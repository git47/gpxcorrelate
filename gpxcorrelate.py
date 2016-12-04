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

nsp = {
    "gpx": "http://www.topografix.com/GPX/1/1",
    "gpxx" : "http://www.garmin.com/xmlschemas/GpxExtensions/v3",
    "gpxspx": "http://www.garmin.com/xmlschemas/TrackStatsExtension/v1",
    "gpxwpx": "http://www.garmin.com/xmlschemas/WaypointExtension/v1",
    "gpxtpx": "http://www.garmin.com/xmlschemas/TrackPointExtension/v1",
}

def hexatupel(gpsstring):
    htupel = []
    for val in gpsstring.split(' '):
        tmp = val.split('/')
        if len(tmp) == 1: tmp.append('1')
        htupel.append(tmp)
    #end for        
    # htupel = [val.split('/') for val in gpsstring.split(',')]
    result = 0.0
    factor = 1.0
    for i in range(len(htupel)):
        result += float(htupel[i][0]) / (factor * float(htupel[i][1]))
        factor *= 60
    #end for
    return result
#end def

def get_exif_from_imagemagick(imgfile):
    exif = {}
    try:
        cp = subprocess.run(["identify", "-format", "'%[EXIF:*]'", imgfile], stdout=subprocess.PIPE, universal_newlines=True)
        exif_stream = cp.stdout.split('\n')
#        exif_stream = subprocess.Popen(["identify", "-format", "'%[EXIF:*]'", imgfile], stdout=subprocess.PIPE, stderr=subprocess.PIPE).communicate()[0].split('\n')
    except:
        return ""
    #end try
    for line in exif_stream:
        reexif = re.match("exif:([^=]*)=(.*)", line)
        if reexif:
            tag, value = reexif.groups()
            exif[tag] = value
        #end if
    #end for
    return exif
#end def

def get_exiv2(imgfile):
    exif = {}
    try:
        cp = subprocess.run(["exiv2", "-pv", imgfile], stdout=subprocess.PIPE, universal_newlines=True)
        exif_stream = cp.stdout.split('\n')
#        exif_stream = subprocess.Popen(["identify", "-format", "'%[EXIF:*]'", imgfile], stdout=subprocess.PIPE, stderr=subprocess.PIPE).communicate()[0].split('\n')
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
    
def get_gps_info(exif):
    try:
        longitude = [1.0,-1.0][exif["GPSLongitudeRef"] == "W"] * hexatupel(exif["GPSLongitude"])
        latitude = [1.0,-1.0][exif["GPSLatitudeRef"] == "S"] * hexatupel(exif["GPSLatitude"])
        altitude = [1.0,-1.0][exif["GPSAltitudeRef"] == "1"] * hexatupel(exif["GPSAltitude"])
    except:
        return ""
    #end try
    return "%f %f %.1f" % (latitude, longitude, altitude)
#end def

def gpxtime2datetime(ts):
    return datetime.datetime(*[int(s) for s in ts.split("T")[0].split('-')+ ts.split("T")[1][:-1].split(":")])
#end def

class Point:
    def __init__(self, timestamp, lon, lat, elev, data=None):
        self.timestamp = timestamp
        self.lon = lon
        self.lat = lat
        self.elev = elev
        self.data = data
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
    def __init__(self):
        self.segment = []
        self.fileno = 0
        self.start = []
        self.end = []
        self.ptno = 0
        pass
    #end def

    def correlate(self, image):
        exif = get_exiv2(image)
        print(image, get_gps_info(exif))
        
        
        
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
    options = {}
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
    print(imagefiles, gpxfiles)
    gpxdata = GPXData()
    for gpxfile in gpxfiles:
        gpxdata.add_file(gpxfile)
    #end if
    for image in imagefiles:
        gpxdata.correlate(image)    
    #end for
'''#
       <trkpt lat="50.1439479925" lon="-5.4180954862">
           <ele>21.77</ele>
           <time>2016-10-26T10:13:08Z</time>
       </trkpt>
'''
        
if __name__ == "__main__":
    main(sys.argv[1:])