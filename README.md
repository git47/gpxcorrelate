# gpxcorrelate

This software is work in progress. Currently, it seems to be working in first tests, but it is lacking a lot of checks and functions.
THIS IS NOT READY NOT FOR PRODUCTIVE USE.

## Synopsis

A simple command line gpx correlator for photos, similar to gpscorrelate.

## Motivation

gpscorrelate is fine, but <s>since it is no longer being developed,</s> I decided to write my own correlator in order to add functions, namely
* correlating additional gpx tags, such as temperature or heart rate,
* adding place names,
* reading multiple gpx files, e.g. parallel recordings from different devices, and map to the closest trackpoint over all files,
* spline interpolation (planned) and perhaps even estimation of directions,
* whatever seems useful and can be implemented with reasonable effort.

## Dependecies

Complete list of dependencies:
* Linux OS or similar
* Python3.x
* evix2 command line version

For a quick start, I decided to use exiv2 for modifying exif tags. I may move to pyexiv later.

## Usage

`python3 gpxcorrelate [-v] [tz=<hours>] [to=<seconds>] [comment=<clear|append>] [place=<true|false>] <gpxfiles> -- <imagefiles>`
* tz: timezone +- 12 hours
* to: time offset in seconds
* place: if true, request a place name from the OSM Nominatim geocoding API. This code respects the restrictions stated at  https://operations.osmfoundation.org/policies/nominatim/. 

## Examples

`gpxcorrelate.py place=true tag=atemp comment=append ~/GPS/Tracks/*.gpx -- *`

Correlate all files in the current directory using all GPX files in ~/GPS/Tracks, using my local timezone. If possible, add a place name from the google maps API to the UserComment EXIF field. When available, also add the temperature value from the XML tag `atemp` to the UserComment.


