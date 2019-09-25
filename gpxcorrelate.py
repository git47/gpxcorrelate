#===============================================================================
# A simple python gpx correlator for photos. gpscorrelate is fine, but since it
# is possible to track information beyond coordinates, e.g. temperature and heart
# rate, I decided to write my own correlator. 
#===============================================================================
import xml.etree.ElementTree as ET
import sys
import re
import os
import subprocess
import datetime
import time
import logging
import gps2name
logging.getLogger("urllib3").setLevel(logging.WARNING)

if __name__ == "__main__":
    logname = "gpxcorrelate.log"
    logging.basicConfig(filename=logname, level=logging.DEBUG,
        format = "%(asctime)s %(levelname)-8s %(name)-20s %(message)s",
        datefmt = "%d %b %Y %H:%M:%S",
        filemode = "w")
    logger = logging.getLogger(logname)    
else:
    logger = logging.getLogger(__file__)
#end if

Tags = {
    "atemp": ["{value}C",], 
}

Nsp = {
    "gpx": "http://www.topografix.com/GPX/1/1",
    "gpxx" : "http://www.garmin.com/xmlschemas/GpxExtensions/v3",
    "gpxspx": "http://www.garmin.com/xmlschemas/TrackStatsExtension/v1",
    "gpxwpx": "http://www.garmin.com/xmlschemas/WaypointExtension/v1",
    "gpxtpx": "http://www.garmin.com/xmlschemas/TrackPointExtension/v1",
}


States = {
    "NONE"              : "",
    "GPS_PRESENT"       : "gps present",
    "INTERPOLATED"      : "interpolated match",
    "EXACT"             : "exact match",
    "SNAPPED"           : "snapped to closest",
    "OVERWRITTEN"       : "old values overwritten",
    "OUT_OF_RANGE"      : "out of range",
    "MULTI"             : "multiple matches",
    "TOO_FAR"           : "too far",
    }
    

def hexatupel_to_gpsrational(ht_string):
    htupel = [val.split('/') for val in ht_string.split()]
    result = 0.0
    factor = 1.0
    for i in range(len(htupel)):
        result += float(htupel[i][0]) / (factor * float(htupel[i][1]))
        factor *= 60
    #end for
    return result
#end def

def gpsrational_to_hexatupel(rational):
    degrees = int(rational)
    minutes = int(60 * (rational - degrees))
    seconds = 3600 * (rational - degrees) - 60 * minutes
    return "{:d}/1 {:d}/1 {:d}/100".format(degrees, minutes, int(100*seconds))
#end def
def set_exiv_comment(imgfile, comment):
#    cp = subprocess.run(['exiv2', '-k', '-Mset Exif.Photo.UserComment charset=Ascii {}'.format(comment), imgfile],stderr=subprocess.PIPE, stdout=subprocess.PIPE)
    cp = subprocess.run(['exiv2', '-k', '-Mset Exif.Photo.UserComment {}'.format(comment), imgfile],stderr=subprocess.PIPE, stdout=subprocess.PIPE)
#end def

def set_exiv_gps(imgfile, lon, lat, alt=None):
    cmdlon = '-Mset Exif.GPSInfo.GPSLongitude {lon}'
    cmdlonref =  '-Mset Exif.GPSInfo.GPSLongitudeRef {lonref}'
    cmdlat = '-Mset Exif.GPSInfo.GPSLatitude {lat}'
    cmdlatref =  '-Mset Exif.GPSInfo.GPSLatitudeRef {latref}'
    cmdalt = '-Mset Exif.GPSInfo.GPSAltitude {alt}'
    cmdaltref = '-Mset Exif.GPSInfo.GPSAltitudeRef {altref}'

    cmd = [
        'exiv2', 
        cmdlon.format(lon=gpsrational_to_hexatupel([lon, -lon][lon < 0.0])),
        cmdlonref.format(lonref=['E','W'][lon < 0.0]),
        cmdlat.format(lat=gpsrational_to_hexatupel([lat, -lat][lat < 0.0])),
        cmdlatref.format(latref=['N','S'][lat < 0.0]),
        cmdalt.format(alt="{:d}/10000".format(int([alt, -alt][alt < 0.0] * 10000.0))),
        cmdaltref.format(altref=int(alt < 0.0)),
        imgfile
    ]
    cp = subprocess.run(cmd, stdout=subprocess.PIPE)
    logging.debug(" ".join(cmd))
    
#end def


def get_exiv2(imgfile):
    exif = {}
    cp = subprocess.run(["exiv2", "-pv", imgfile], stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
    if cp.returncode == 0:
        exif_stream = cp.stdout.split('\n')
    else:
        return ""
    #end if
    for line in exif_stream:
        # reexif = re.match("(0x[0-9a-f]{4})\s+(\w+)\s+(\w+)\s+(\d+)\s+(.*)", line)
        reexif = re.match("0x[0-9a-f]{4}\s+\w+\s+(\w+)\s+\w+\s+\d+\s+(.*)", line)
        if reexif:
            tag, value = reexif.groups()
            exif[tag] = value
        #end if
    #end for
    return exif
#end def

class GpsInfo:
    def __init__(self, exif):
        self.longitude = self.latitude = self.altitude = None
        try: self.longitude = [1.0,-1.0][exif["GPSLongitudeRef"] == "W"] * hexatupel_to_gpsrational(exif["GPSLongitude"])
        except: pass
        try: self.latitude = [1.0,-1.0][exif["GPSLatitudeRef"] == "S"] * hexatupel_to_gpsrational(exif["GPSLatitude"])
        except: pass
        try:self.altitude = [1.0,-1.0][exif["GPSAltitudeRef"] == "1"] * hexatupel_to_gpsrational(exif["GPSAltitude"])
        except: pass
    #end def
    def __str__(self):
        if self.longitude is None: lon = "{:8s}".format("-")
        else: lon = "{:8.4f}".format(self.longitude)
        if self.latitude is None: lat = "{:8s}".format("-")
        else: lat = "{:8.4f}".format(self.latitude)
        if self.altitude is None: alt = "{:4s}".format("-")
        else: alt = "{:4.0f}".format(self.altitude)
        return "{} {} {}".format(lon, lat, alt)
    #end def
    def has_coordinates(self):
        return self.longitude != None and self.latitude != None
    #end def
#end class

def gpxtime2datetime(ts):
    return datetime.datetime(*[int(s) for s in ts.split("T")[0].split('-')+ ts.split("T")[1][:-1].split(":")])
#end def

def exiftime2datetime(ts):
    rets = re.match("(\d\d\d\d):(\d\d):(\d\d) (\d\d):(\d\d):(\d\d)", ts)
    return datetime.datetime(*[int(s) for s in rets.groups()])
#end def

class Point:
    def __init__(self, timestamp, lon, lat, elev, data=None):
        self.timestamp = timestamp
        self.lon = lon
        self.lat = lat
        self.elev = elev
        self.data = data
    #end def
    def get_gpsinfo(self):
        return(self.lon, self.lat, self.elev)
    #end def
    def get_data(self):
        return self.data
    #end def
#end class

class Segment:
    def __init__(self):
        self.start = None
        self.end = None
        self.points = []
    #end def
    def __len__(self):
        return(len(self.points))
    #end def
    def add_point(self, point):
        self.points.append(point)
        if self.start is None or self.start > point.timestamp:
            self.start = point.timestamp
        #end if
        if self.end is None or self.end < point.timestamp:
            self.end = point.timestamp
        #end if
#end def

class GPXData:
    def __init__(self, tz=0, to=0):
        self.tz = tz
        self.tz_offset = datetime.timedelta(0, 3600*tz, 0)
        self.to = to
        self.to_offset = datetime.timedelta(0, to, 0)
        self.segment = []
        self.fileno = 0
        self.start = []
        self.end = []
        self.ptno = 0
        pass
    #end def
    
    def correlate(self, image, maxdiff=60, tag=None, interpolate=False, overwrite=False):
        state = set()
        md_offset = datetime.timedelta(0, maxdiff, 0)
        ex_offset = datetime.timedelta(0, 1, 0)
        exif = get_exiv2(image)
        if exif == "":
            logging.warn("{}: no exif data - skipped.".format(image))
            return None
        #end if
        old_gps = GpsInfo(exif)
        if old_gps.has_coordinates(): state.add("GPS_PRESENT")
        dt_original = exif['DateTimeOriginal']
        dto = exiftime2datetime(dt_original)
        dtzulu = dto - self.tz_offset - self.to_offset
        matches = []
        offsets = []
        for segment in self.segment:
            if dtzulu < segment.start or dtzulu > segment.end: continue
            start = 0
            end = len(segment.points)-1
            match = None
            while True:
                if (end - start) <= 1:
                    off_start = segment.points[start].timestamp - dtzulu
                    off_end = segment.points[end].timestamp - dtzulu
                    if interpolate is True:
                        print("Interpolation not yet implemented")
                    #end if
                    if segment.points[end].timestamp - dtzulu < dtzulu - segment.points[start].timestamp:
                        match = segment.points[end]
                        offset = off_end
                    else:
                        match = segment.points[start]
                        offset = off_start
                    #end if
                    if match is not None:
                        matches.append(match)
                        offsets.append(offset)
                    #end if
                    break
                #end if
                mid = (start + end) // 2
                if dtzulu < segment.points[mid].timestamp:
                    end = mid
                else:
                    start = mid
                #end if
            #end while
        #end for
        found = None
        for matchno in range(len(matches)):
            if offsets[matchno] > md_offset:
                state.add("TOO_FAR")
                continue
            #end if
            if offsets[matchno] < ex_offset:
                state.add("EXACT")
            else:
                state.add("SNAPPED")
            #end if
            if found is None or offsets[matchno] < offsets[found]:
                found = matchno
            #end if
            mlon, mlat, mele = [float(x) for x in matches[found].get_gpsinfo()]
            logging.info("{:s}: matched: {:8.4f} {:8.4f} {:4.0f} error: {:2d}s, old: {:s}".format(image, mlon, mlat, mele, int(offsets[found].total_seconds()), str(old_gps)))
            set_exiv_gps(image, mlon, mlat, mele)
            return [matches[found], exif]
        #end for
        logging.info("{:s}: matched: {:8s} {:8s} {:4s} error: {:2s}s, old: {:s}".format(image, "-", "-", "-", "-", str(old_gps)))
        return None
    #end def
        
    def add_segment(self, segment):
        self.segment.append(segment)
        if self.start > segment.timestamp:
            self.start = segment.timestamp
        #end if
        if self.end < segment.timestamp:
            self.end = segment.timestamp
        #end if
    #end def
    
    def add_file(self, gpxfile, tags=[]):
        logging.info("adding gpx: {}".format(gpxfile))
        try:
            gpx = open(gpxfile, 'r')
        except:
            logging.error("{}: cannot open file for reading - skipped.".format(gpxfile))
            return
        #end try
        try:
            tree = ET.parse(gpx)
            gpx = tree.getroot()
        except:
            logging.error("{}: no xml root found - skipped.".format(gpxfile))
            return
        #end try

        self.fileno += 1
                
        trackno = 0
        for track in gpx.findall('gpx:trk', Nsp):
            trackno += 1
            try:
                name = track.find('gpx:name', Nsp).text
                logging.info("{}: track name is '{}'".format(gpxfile, name))
            except:
                logging.warn("{}: no track name".format(gpxfile))
            #end try

            segno = 0
            for seg in track.findall('gpx:trkseg', Nsp):
                segment = Segment()
                segno += 1
                for pt in seg.findall('gpx:trkpt', Nsp):
                    self.ptno += 1
                    lon = pt.get("lon")
                    lat = pt.get("lat")
                    data = {}
                    try:
                        ele = pt.find("gpx:ele", Nsp).text
                    except:
                        logging.debug("{}: no elevation for {},{}".format(gpxfile, lon, lat))
                    #end try                        
                    try:
                        ts = pt.find("gpx:time", Nsp).text
                    except:
                        logging.debug("{}: no timestamp for {},{} - track point skipped.".format(gpxfile, lon, lat))
                        continue
                    #end try
                    timestamp = gpxtime2datetime(ts)
                    for tag in tags: 
                        try: 
                            data[tag] = pt.find(".//gpxtpx:{}".format(tag), Nsp).text
                        except: pass
                    #end if
                    point = Point(timestamp, lon, lat, ele, data)
                    segment.add_point(point)
                #end for
                if len(segment) == 0:
                    logging.warn("{}: segment does not contain enough data for correlation - skipped.".format(gpxfile))
                else:
                    self.segment.append(segment)
                    logging.info("{}: {} points added.".format(gpxfile, len(segment)))
                #end if
            #end for
        #end for
    #end def
#end class

def help():
    print("usage: gpxcorrelate [-v] [tz=<hours>] [to=<seconds>] [place=<true|false>] <gpxfiles> -- <imagefiles>")
    print("tz: timezone +- 12 hours")
    print("to: time offset in seconds")
#end def
    
def main(args):
    global logger
    options = {
        'tz': str(-time.timezone//3600),
        'to': '0',
        'tag' : [],
        'comment' : 'append',
        }
    url_cache = gps2name.Urlcache()
    gpxfiles = []
    imagefiles = []
    files = gpxfiles
    for arg in args:
        match = re.match("--?h.*", arg)
        if match is not None:
            help()
            return
        #end if
        match = re.match("-(\w)", arg)
        if match is not None:
            key = match.groups()[0]
            options[key] = "set"
            continue
        #end if
        match = re.match("(\w+)=(.+)", arg)
        if match is not None:
                
            key, val = match.groups()
            if key == 'tag':
                options['tag'].append(val)
            else:
                options[key] = val
            #end if
            continue
        #end if
        if arg == "--":
            files = imagefiles
            continue
        #end if
        files.append(arg)
    #end for
    if 'v' in options:
        logger = logging.getLogger()
        logger.setLevel(logging.DEBUG)
        strhd = logging.StreamHandler(sys.stdout)
        strhd.setLevel(logging.INFO)
        formatter = logging.Formatter("%(message)s")
        strhd.setFormatter(formatter)
        logger.addHandler(strhd)
    #end if
    try:
        tz = int(options['tz'])
    except:
        print("{} is not a valid timezone offset (-12 .. +12)".format(tz))
    #end try
    try:
        to = int(options['to'])
    except:
        print("{} is not a valid time offset (number of seconds)".format(tz))
    #end try
    gpxdata = GPXData(tz, to)
    for gpxfile in gpxfiles:
        gpxdata.add_file(gpxfile, tags=options['tag'])
    #end if
    for image in imagefiles:
        result = gpxdata.correlate(image, maxdiff=300)
        if result is None: continue
        lon, lat, ele = result[0].get_gpsinfo()
        data = result[0].get_data()
        exif = result[1]
        if options['comment'] == "clear":
            comment = newcomment = ""
        else:
            try:
                comment = newcomment = exif['UserComment']
            except:
                logger.warn('{}: missing UserComment exif tag'.format(image))
                comment = newcomment = ""
            #end try
        #endif
        if len(comment) == 0:
            delimiter = ""
        else:
            delimiter = ", "
        #end if 
        if 'place' in options and options['place'].lower() in ('yes', 'true', '1'):
            #status, place = gps2name.gps2name(lon, lat)
            place = gps2name.gps2name(float(lat), float(lon), image=os.path.basename(image), url_cache=url_cache)
            if place is not None and not place in newcomment:
                newcomment = newcomment + delimiter + place
                delimiter = ", "
            #end if
        #end if
        for tag in options['tag']:
            try:
                formatted_value = Tags[tag][0].format(value=data[tag])
            except:
                try:
                    formatted_value = "{}={}".format(tag, data[tag])
                except:
                    formatted_value = None
                #end try
            #end try
            if tag in data and not formatted_value is None and not formatted_value in newcomment:   
                newcomment = newcomment + delimiter + formatted_value
                delimiter = ", "
            #end if
        #end for
        if newcomment != comment:
            logging.debug("UserComment '{}' -> '{}'".format(comment, newcomment))
            set_exiv_comment(image, newcomment)
        #end if
    #end for
        
if __name__ == "__main__":
    main(sys.argv[1:])
