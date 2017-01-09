# gpxcorrelate

## Synopsis

A simple command line gpx correlator for photos, similar to gpscorrelate.


## Motivation

gpscorrelate is fine, but since it is no longer being developed, I decided to write my own correlator in order to add functions, namely
* correlating additional gpx tags, such as temperature or heart rate,
* adding place names,
* reading multiple gpx files, e.g. parallel recordings from different devices, and map to the closest trackpoint over all files,
* spline interpolation (planned) and perhaps even estimation of directions,
* whatever seems useful and be implemented with reasonable effort.


is possible to track information beyond coordinates, e.g. temperature and heart
rate, I decided to write my own correlator.


Currently developed and tested on Linux, it will be portable in th future.