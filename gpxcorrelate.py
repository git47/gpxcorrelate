#===============================================================================
# A simple python gpx correlator for photos. gpscorrelate is fine, but since it
# is possible to track information beyond coordinates, e.g. temperature and heart
# rate, I decided to write my own correlator. 
#===============================================================================
import xml.etree.ElementTree as ET
import sys
import glob
import re
import subprocess
import datetime
from math import degrees

nsp = {
    "gpx": "http://www.topografix.com/GPX/1/1",
    "gpxx" : "http://www.garmin.com/xmlschemas/GpxExtensions/v3",
    "gpxspx": "http://www.garmin.com/xmlschemas/TrackStatsExtension/v1",
    "gpxwpx": "http://www.garmin.com/xmlschemas/WaypointExtension/v1",
    "gpxtpx": "http://www.garmin.com/xmlschemas/TrackPointExtension/v1",
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
    return "{d}/1 {d}/1 {d}/100".format(degrees, minutes, int(100*seconds))
#end def

def set_exiv_gps(imgfile, lon, lat, alt=None):
    cmdlat = '-M"set Exif.GPSInfo.GPSLatitude {lat}" -M"set Exif.GPSInfo.GPSLatitudeRef {latref}"'
    cmdlon = '-M"set Exif.GPSInfo.GPSLatitude {lon}" -M"set Exif.GPSInfo.GPSLatitudeRef {lonref}"'
    cmdalt = '-M"set Exif.GPSInfo.GPSAltitude {alt}"'

    cmd = [
        'exiv2', 
        cmdlon.format(lon=gpsrational_to_hexatupel(lon), lonref=['N','S'][lon < 0.0]),
        cmdlat.format(lat=gpsrational_to_hexatupel(lat), latref=['W','E'][lat < 0.0]),
        cmdalt.format(lat=gpsrational_to_hexatupel(alt)),
        imgfile
    ]
    try:
        cp = subprocess.run(cmd, stdout=subprocess.PIPE, universal_newlines=True)
    except:
        return ""
    #end try
#end def
    

def get_exiv2(imgfile):
    exif = {}
    try:
        cp = subprocess.run(["exiv2", "-pv", imgfile], stdout=subprocess.PIPE, universal_newlines=True)
        exif_stream = cp.stdout.split('\n')
    except:
        return ""
    #end try
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
def get_gps_info(exif):
    try:
        longitude = [1.0,-1.0][exif["GPSLongitudeRef"] == "W"] * hexatupel_to_gpsrational(exif["GPSLongitude"])
        latitude = [1.0,-1.0][exif["GPSLatitudeRef"] == "S"] * hexatupel_to_gpsrational(exif["GPSLatitude"])
        altitude = [1.0,-1.0][exif["GPSAltitudeRef"] == "1"] * hexatupel_to_gpsrational(exif["GPSAltitude"])
    except:
        return []
    #end try
    return (latitude, longitude, altitude)
#end def

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
        return(self.lat, self.lon, self.elev)
    #end def
#end class

class Segment:
    def __init__(self):
        self.start = None
        self.end = None
        self.points = []
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
    
    def correlate(self, image, maxdiff=60, interpolate=False, overwrite=False):
        state = set()
        md_offset = datetime.timedelta(0, maxdiff, 0)
        ex_offset = datetime.timedelta(0, 1, 0)
        exif = get_exiv2(image)
        old_gps = get_gps_info(exif)
        if len(old_gps) > 0: state.add("GPS_PRESENT")
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
                    off_start = segment.points[end].timestamp - dtzulu
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
                mid = (end + start) // 2
                if dtzulu < segment.points[mid].timestamp:
                    end = mid
                else:
                    start = mid
                #end if
                print(start, mid, end)
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
            return (matches[found].get_gpsinfo(), old_gps, offsets[found].total_seconds(), state)

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
    
    def add_file(self, gpxfile):
        with open(gpxfile, 'r') as gpx:
            self.fileno += 1
            tree = ET.parse(gpx)
            gpx = tree.getroot()
            trackno = 0
            for track in gpx.findall('gpx:trk', nsp):
                trackno += 1
                name = track.find('gpx:name', nsp).text
                segno = 0
                for seg in track.findall('gpx:trkseg', nsp):
                    segment = Segment()
                    segno += 1
                    for pt in seg.findall('gpx:trkpt', nsp):
                        self.ptno += 1
                        lat = pt.get("lat")
                        lon = pt.get("lon")
                        data = {}
                        ele = pt.find("gpx:ele", nsp).text
                        ts = pt.find("gpx:time", nsp).text
                        timestamp = gpxtime2datetime(ts) 
                        try: data['atemp'] = pt.find(".//gpxtpx:atemp", nsp).text
                        except: pass
                        #end if
                        point = Point(timestamp, lon, lat, ele, data)
                        segment.add_point(point)
                    #end for
                    self.segment.append(segment)
                #end for
            #end for
        #end with
    #end def
#end class

def main(args):
    options = {
        'tz': '0',
        'to': '0',
        }
    gpxfiles = []
    imagefiles = []
    files = gpxfiles
    for arg in args:
        match = re.match("(\w)+=(.+)", arg)
        if match is not None:
            key, val = match.groups()[1:3]
            options[key] = val
            continue
        #end if
        if arg == "--":
            files = imagefiles
            continue
        #end if
        files.append(arg)
    #end for
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
    print(imagefiles, gpxfiles)
    gpxdata = GPXData(tz, to)
    for gpxfile in gpxfiles:
        gpxdata.add_file(gpxfile)
    #end if
    for image in imagefiles:
        res = gpxdata.correlate(image)
        print(res)
    #end for
        
if __name__ == "__main__":
    main(sys.argv[1:])