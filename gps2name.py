#===============================================================================
# A simple nominatim-based python gps locator for photos.
# Please see the usage policies of Nominatim at
# [1] https://wiki.openstreetmap.org/wiki/Nominatim
# Especially, do NOT use this script for geolocating large collections of
# photos. According to [1], a couple of 100s of holiday photos once or
# twice a year should be OK.
# I implemented a caching algorithm as required. After each cache miss and
# subsequent Nominatim call, the script sleeps for 2 seconds.
#===============================================================================
import os
import datetime
import json
import time
import logging
import requests
logging.getLogger("urllib3").setLevel(logging.WARNING)

class Urlcache:
    def __init__(self):
        self.cache = os.path.join(os.environ["HOME"], ".cache", "nominatim_urls.json")
        self.gps_cache = {}
        self.bb_cache = {}
        try:
            open(self.cache,'r').close()
        except:
            try:
                open(self.cache,'w').close()
            except:
                logger.warn("could not open {}. Caching disabled.".format(self.cache))
                self.enabled = False
            #end try
        #end try
        try:
            f = open(self.cache, 'r')
            self.gps_cache = json.load(f)
            f.close()
        except:
            self.gps_cache = {}
        #end try
        self.build_bb_cache()
    #end def
    
    def save(self):
        with open(self.cache, "w") as f:
            json.dump(self.gps_cache, f, indent=0)
        #end with
    
    def add_to_bb_cache(self, lat, lon):
        bb_key = "{:.2f}:{:.2f}".format(lat, lon)
        gps_key = "{:.4f}:{:.4f}".format(lat, lon)
        if not gps_key in self.bb_cache.get(bb_key, []): 
            try:
                self.bb_cache[bb_key].append(gps_key)
            except:
                self.bb_cache[bb_key] = [gps_key,]
            #end try
        #end if
    #end def
    
    def add_to_gps_cache(self, lat, lon, data):
        gps_key = "{:.4f}:{:.4f}".format(lat, lon)
        self.gps_cache[gps_key] = data
    #end def
        
    def build_bb_cache(self):
        for key in self.gps_cache:
            data = self.gps_cache[key]
            bb_key = "{:.2f}:{:.2f}".format(float(data['lat']), float(data['lon']))
            try:
                self.bb_cache[bb_key].append(key)
            except:
                self.bb_cache[bb_key] = [key,]
            #end try
        #end for
    #end def

    def get_from_gps_cache(self, lat, lon):
        gps_key = "{:.4f}:{:.4f}".format(lat, lon)
        try:
            return self.gps_cache[gps_key]
        except:
            return None
        #end try
    #end def

    def get_from_bb_cache(self, lat, lon):
        
        bb_key = "{:.2f}:{:.2f}".format(lat, lon)
        try:
            bb_list = self.bb_cache[bb_key]
        except:
            return None
        #end try
        for gps_key in bb_list:
            data = self.gps_cache[gps_key]
            lat1, lat2, lon1, lon2 = [float(s) for s in data["boundingbox"]]
            lat1a = lat1 + (lat2 - lat1) * 0.25
            lat2a = lat1 + (lat2 - lat1) * 0.75
            lon1a = lon1 + (lon2 - lon1) * 0.25
            lon2a = lon1 + (lon2 - lon1) * 0.75
            print(lat, lon, data["boundingbox"], lat1, lat2, lon1, lon2, lat1 <= lat, lat2 >= lat, lon1 <= lon, lon2 >= lon)
            if lat1a <= lat and lat2a >= lat and lon1a <= lon and lon2a >= lon:
                return data
            #end if
        #end for
        return None
    #end def
#end class

def get_from_nominatim(lat, lon):        
    url="https://nominatim.openstreetmap.org/reverse?format=jsonv2&lat={}&lon={}".format(lat, lon)
    response = requests.get(url.format(lat, lon))
    time.sleep(2)
    #text = response.read()
    text = response.content
    return json.loads(str(text, 'utf-8'))
#end def
    
def gps2name(lat, lon, image, url_cache):
    # try exact cache hits first
    place_data = url_cache.get_from_gps_cache(lat, lon)
    if place_data is not None:
        if not image in place_data['used']:
            place_data['used'].append(image)
        #end if
#         n_data = get_from_nominatim(lat, lon)
#         if n_data["place_id"] != place_data["place_id"]:
#             print ("\n{}:\n{}\n{}\n\n".format(image, n_data["display_name"], place_data["display_name"]))
#         #end if
        print('[cached: {} used: {}] {}: {}'.format(place_data['cached'], len(place_data['used']), image, place_data['display_name']))
        return place_data['display_name']
    #end if
    place_data = get_from_nominatim(lat, lon)
    place_data['cached'] = datetime.date.isoformat(datetime.datetime.now())
    place_data['used'] = [image]
    #name = place_data['results'][0]['formatted_address']
    name = place_data['display_name']
    print('[nominatim] {}: {}'.format(image, name))
    url_cache.add_to_gps_cache(lat, lon, place_data)
    url_cache.add_to_bb_cache(lat, lon)
    url_cache.save()
    return name
#end def

