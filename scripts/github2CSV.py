#!/usr/bin/env python

from github import Github
from pathlib import Path
import datetime
import csv
import sys
from lxml import html
import json
import yaml
import configparser
import os
import io
import logging

import pandas as pd
import geopandas as gpd
from shapely.geometry import Point

# Configure logger to print log message to stdout
logformat = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
logging.basicConfig(stream=sys.stdout, level=logging.INFO, format=logformat)
logger = logging.getLogger('github2CSV')

csv_column_names = ["url","id","updated_at","created_at","title","lat","lon","regione","provincia","labels","milestone","image","data","body","state"]

# Program arguments
CSVFILE=sys.argv[1]
try:
    JSONFILE=sys.argv[2]
    jwr=io.open(JSONFILE,"r+",encoding="utf-8")
except:
    jwr=None

try:
    GEOJSONFILE=sys.argv[3]
    gjwr=io.open(GEOJSONFILE,"w+",encoding="utf-8")
except:
    gjwr=None

LIMITIPATH=sys.argv[4]

try:
    ACCETTATOLABEL=sys.argv[5]
except:
    ACCETTATOLABEL="Accettato"

FILTER_LABELS=("Accettato","accepted")
POSIZIONE_NAMES=("posizione","Posizione","position","Position","location","Location")

TMPCSVFILE = '../_data/issues_temp.csv'
TMPJSONFILE = '../_data/issuesjson_temp.json'
TMPGEOJSONFILE = '../_data/issues_temp.geojson'

# Default values for repository name and Github organization
# They are used if an error occurred while reading values
# from configuration file
REPO_NAME='covid19italia_segnalazioni'
ORG='emergenzeHack'

def get_github_client():
    try:
        config=configparser.RawConfigParser()
        config.read('.github.cfg')

        TOKEN=None
        PASS=config.get('GitHub','TOKEN')
        USER=config.get('GitHub','USER')
        REPO_NAME=config.get('GitHub','REPO_NAME')
        ORG=config.get('GitHub','ORG')
    except:
        TOKEN=os.environ.get('GITHUB_TOKEN')
        PASS=os.environ.get('GITHUB_PASSWORD')
        USER=os.environ.get('GITHUB_USERNAME')

    if not TOKEN:
        if not PASS:
            logger.error("Need a TOKEN")
            sys.exit(1)

        if not USER:
            logger.error("Need a USER")
            sys.exit(1)

    if not REPO_NAME:
        logger.error("Need a REPO_NAME")
        sys.exit(1)

    if not ORG:
        logger.error("Need a ORG")
        sys.exit(1)

    if TOKEN:
        return Github(TOKEN)
    
    return Github(USER, PASS)


def get_latest_timestamp(csvfile):
    df = pd.read_csv(csvfile, index_col='id', names=csv_column_names, header=None, sep=',')
    # sort rows by updated_at timestamp and parse it, in order to return a datetime instance
    data = df.sort_values(by='updated_at', ascending=False)

    if not data['updated_at'][1:-1].empty:
        max_updated_at = max(data['updated_at'][1:-1])
        return datetime.datetime.strptime(max_updated_at, '%Y-%m-%d %H:%M:%S')

    return datetime.datetime(2000,1,1)

def write_output_files(geojsonarray, issues):
    write_csv_file(issues)
    if jwr:
        write_json_file(issues)
    if gjwr:
        write_geojson_file(geojsonarray, issues)

def write_csv_file(issues):
    with open(CSVFILE, "r+") as current_file, open(TMPCSVFILE, "w+") as output_file:
        csvwriter = csv.writer(output_file, quotechar='"')
        csvreader = csv.reader(current_file)
        next(csvreader, None)   # skip the header

        csvwriter.writerow(tuple(csv_column_names)) # write CSV header columns
        for line in csvreader:
            issue_id = int(line[1])
            if issue_id in issues:
                # the issue has been updated, we need to update it in our CSV file 
                issue = issues[issue_id]
                gh_issue = issue["issue"] # Github issue instance
                logger.info("[CSV] Updating issue {}...".format(issue_id))
                row = (gh_issue.html_url,issue_id,gh_issue.updated_at,gh_issue.created_at,issue["title"],issue["lat"],issue["lon"],issue["regioneIssue"],issue["provinciaIssue"],issue["labels"],gh_issue.milestone,issue["image"],json.dumps(issue["data"],sort_keys=True),gh_issue.body, gh_issue.state)
                del issues[issue_id]
            else:
                # otherwise, just append the existing row without modifying it
                row = line
            csvwriter.writerow(row)
        
        for issue_id in issues: # append the remaining new issues
            issue = issues[issue_id]
            gh_issue = issue["issue"] # Github issue instance
            logger.info("[CSV] Writing new issue {}...".format(issue_id))
            row = (gh_issue.html_url,issue_id,gh_issue.updated_at,gh_issue.created_at,issue["title"],issue["lat"],issue["lon"],issue["regioneIssue"],issue["provinciaIssue"],issue["labels"],gh_issue.milestone,issue["image"],json.dumps(issue["data"],sort_keys=True),gh_issue.body, gh_issue.state)
            csvwriter.writerow(row)
    # move temp file to final one
    Path(TMPCSVFILE).rename(CSVFILE)

def write_json_file(issues):
    jsonarray = []
    with open(TMPJSONFILE, "w+") as output_file:
        data = json.load(jwr)
        for row in data:
            issue_id = row["issue"]["id"]
            if issue_id in issues:
                # the issue has been updated, we need to update it in our JSON file
                issue = issues[issue_id]
                gh_issue = issue["issue"]
                logger.info("[JSON] Updating issue {}...".format(issue_id))
                jsonarray.append(get_json_issue(issue, gh_issue))
                del issues[issue_id]
            else:
                # otherwise, just append the existing row without modifying it
                jsonarray.append(row)
         
        for issue_id in issues: # append the remaining new issues
            issue = issues[issue_id]
            gh_issue = issue["issue"]
            logger.info("[JSON] Writing new issue {}...".format(issue_id))
            jsonarray.append(get_json_issue(issue, gh_issue))

        output_file.write(json.dumps(jsonarray,ensure_ascii=False,sort_keys=True))
    # move temp file to final one
    Path(TMPJSONFILE).rename(JSONFILE)
    

def get_json_issue(issue, gh_issue):
    return {
        "title":gh_issue.title,
        "number":gh_issue.number,
        "state":gh_issue.state,
        "issue":{
            "url":gh_issue.html_url,
            "id":gh_issue.id,
            "updated_at":gh_issue.updated_at.isoformat()+"+00:00",
            "created_at":gh_issue.created_at.isoformat()+"+00:00",
            "title":issue["title"],
            "lat":issue["lat"],
            "lon":issue["lon"],
            "regione":issue["regioneIssue"],
            "provincia":issue["provinciaIssue"],
            "labels":issue["labels"],
            "milestone":gh_issue.milestone.title if gh_issue.milestone else None,
            "image":issue["image"],
            "data":issue["data"],
            "body":gh_issue.body}
    }

def write_geojson_file(geojsonarray, issues):
    gjwr.write(str('{ "type": "FeatureCollection", "features": '))
    gjwr.write(json.dumps(geojsonarray,ensure_ascii=False,sort_keys=True)+"}")

def get_geojson_issue(issue, gh_issue):
    return {
        "type":"Feature",
        "geometry":{
            "type":"Point",
            "coordinates":[issue["lon"],issue["lat"]]},
            "properties":{
                "title":gh_issue.title,
                "number":gh_issue.number,
                "state":gh_issue.state,
                "url":gh_issue.html_url,
                "id":gh_issue.id,
                "updated_at":gh_issue.updated_at.isoformat()+"+00:00",
                "created_at":gh_issue.created_at.isoformat()+"+00:00",
                "labels":eval(issue["labels"]) if issue["labels"] else None,
                "milestone":gh_issue.milestone.title if gh_issue.milestone else None,
                "image":image,
                "data":issue["data"],
                "body":gh_issue.body,
                "regione":issue["regioneIssue"],
                "provincia":issue["provinciaIssue"]
            }
        }

if __name__ == "__main__":
    logger.info("Reading 'regioni' geo data file...")
    regioni=gpd.read_file(LIMITIPATH+"/Limiti01012019_g/Reg01012019_g/Reg01012019_g_WGS84.shp")

    regioni=gpd.GeoDataFrame(regioni)
    regioni.crs='epsg:23032'
    regioni=regioni.to_crs('epsg:4326')

    logger.info("Reading 'province' geo data file...")
    province=gpd.read_file(LIMITIPATH+"/Limiti01012019_g/ProvCM01012019_g/ProvCM01012019_g_WGS84.shp")

    province=gpd.GeoDataFrame(province)
    province.crs='epsg:23032'
    province=province.to_crs('epsg:4326')

    logger.info("Reading Github configration...")
    g = get_github_client()

    org = g.get_organization(ORG)
    r = org.get_repo(REPO_NAME)

    filter_labels=[]
    for l in FILTER_LABELS:
        try:
            ghlabel=r.get_label(l)
            filter_labels.append(ghlabel)
        except:
            pass

    logger.info("Retrieving latest updated_at timestamp from our issues file ({0})...".format(CSVFILE))
    latestTimestamp = get_latest_timestamp(CSVFILE)
    # we need to add one second to the latest timestamp in our issue file
    # to avoid retrieving the "last" issue we already have (in the issues file)
    lastTime = latestTimestamp + datetime.timedelta(seconds=1)

    logger.info("Retrieving issues from Github (since {0})...".format(lastTime))
    issues=r.get_issues(since=lastTime,labels=filter_labels,state='all',sort='updated')
    logger.info("{0} issues retrieved...".format(issues.totalCount))

    issuedict={}
    geojsonarray=[]

    for issue in issues:
        labels = json.dumps([l.name for l in issue.labels])
        data={}
        lat = lon = image = regioneIssue = provinciaIssue = None

        try:
            tree=html.fromstring(issue.body)

            try:
                dataRaw=tree.xpath("//data/text()")
                dataStr=dataRaw[0] if len(dataRaw) > 0 else None
                data=json.loads(dataStr)
            except:
                pass

            try:
                yamldataRaw=tree.xpath("//yamldata/text()")
                yamldataStr=yamldataRaw[0] if len(yamldataRaw) > 0 else None
                data=yaml.safe_load(yamldataStr)
            except:
                pass
        except:
            pass

        if not data:
            logger.info("Data not found for issue {issue}.".format(issue=issue))
            continue

        for posName in POSIZIONE_NAMES:
            if posName in data:
                try:
                    (lat,lon) = data[posName].split(" ")[:2]
                    p = Point(float(lon),float(lat))
                    for i,regione in regioni.iterrows():
                        if regione['geometry'].contains(p):
                            regioneIssue = regione["DEN_REG"]
                            break

                    for i,provincia in province.iterrows():
                        if provincia['geometry'].contains(p):
                            provinciaIssue = provincia["DEN_UTS"]
                            break

                except Exception as e:
                    logger.error("Exception: %s", e)
                break

        if "regione_manuale" in data:
            regioneIssue = data["regione_manuale"]

        if "provincia_manuale" in data:
            provinciaIssue = data["provincia_manuale"]

        if "immagine" in data:
            image=data['immagine']

        title=issue.title
        if title is not None:
            title=title

        labels=labels

        issuedict[issue.id] = {
            "issue": issue,
            "title": title,
            "lat": lat,
            "lon": lon,
            "regioneIssue": regioneIssue,
            "provinciaIssue": provinciaIssue,
            "labels": labels,
            "image": image,
            "data": data
        }
        
        if gjwr:
            geojsonarray.append({"type":"Feature","geometry":{"type":"Point","coordinates":[lon,lat]},"properties":{"title":issue.title,"number":issue.number,"state":issue.state,"url":issue.html_url,"id":issue.id,"updated_at":issue.updated_at.isoformat()+"+00:00","created_at":issue.created_at.isoformat()+"+00:00","labels":eval(labels) if labels else None,"milestone":issue.milestone.title if issue.milestone else None,"image":image,"data":data,"body":issue.body,"regione":regioneIssue,"provincia":provinciaIssue}})

    write_output_files(geojsonarray, issuedict)
