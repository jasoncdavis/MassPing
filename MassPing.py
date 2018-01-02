#!/usr/local/bin/python3.6

"""
MassPing.py

script loading a file with a list of devices to ping, then pings the devices, then puts
the results into a webpage

v1	2017-1217	jadavis Initial version
"""

import shlex
from subprocess import check_output, Popen, PIPE
import re
import requests
import sys #needed for sys.exit
import schedule
import time
import datetime


## User defined vars
devicelist = "devicelist.txt"
htmlcolumncount = 20 #Number of columns in a table
warningratio = 0.5   #number of millisecond where a HIGHER number (ms) reports yellow/warning
influxserver = "localhost" #hostname or IP of InfluxDB server
databasename = "RTPNML"     #name of existing InfluxDB database
dashboardfilename = "/var/www/html/availability.html"
##

## Other script variables
starthtml = '''<html>
<head>
	<META HTTP-EQUIV="refresh" CONTENT="5" />
	<title>CiscoLive NOC Device Availability Dashboard</title>
</head>
<style>

body { font-size: 62.5%; }

table {
    font-family: arial, sans-serif;
    border-collapse: collapse;
    width: 100%;
}

td, th {
    border: 1px solid #dddddd;
    text-align: center;
    padding: 8px;
    font-size: 33.3%;
}

tr:nth-child(even) {
    background-color: #dddddd;
}

.upgreen {
	background-color: lime;
	color: black;
}

.warnyellow {
	background-color: yellow;
	color: black;
}

.downred {
	background-color: red;
	color: white;
}
</style>
</head>
<body>

<table>
<tr>
'''

endtable = '''</tr>
</table>
'''


def get_fping_output(cmd):
	args = shlex.split(cmd)
	proc = Popen(args, stdout=PIPE, stderr=PIPE, encoding='utf8')
	out, err = proc.communicate()
	exitcode = proc.returncode
	return exitcode, out, err


def load_devicefile():
	iplist = dict()
	with open(devicelist) as file:
		for line in file:
			line = line.strip() #preprocess line
			ipaddress, hostname, location, function = line.split()
			iplist[ipaddress] = [hostname,location,function]
	return iplist

def getpingresults():
	iplist = dict(load_devicefile())
	cmd = "/usr/bin/fping -C 1 -A -d -q {}".format(" ".join(map(str, iplist.keys())))
	exitcode, out, results = get_fping_output(cmd)
	
	pingresults = []
	for aline in results.split("\n"):
		if aline:
			m = re.match(r"(\S+) \((\S+)\)\s+\:\s(\S+)", aline)
			hostname = m.group(1).replace('.rtpnml.cisco.com','')
			ipaddress = m.group(2)
			rtt = m.group(3)
			if rtt == '-':
				iplist[ipaddress] += (float(9999),)
			elif float(rtt) > warningratio:
				iplist[ipaddress] += (float(rtt),)
			else:
				iplist[ipaddress] += (float(rtt),)
	
	sorted_iplist = sorted(iplist.items(), key=lambda k: k[1][3], reverse=True)
	return sorted_iplist

def createtabledata():
	ts = time.time()
	timenow = datetime.datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S')
	sorted_iplist = getpingresults()
	html = starthtml
	influxdata = []
	columncount = 0
	influxlaunch = 'http://10.122.6.10:3000/dashboard/db/ping-results?panelId=1&fullscreen&orgId=1&from=now-1h&to=now&var-host='
	for key in sorted_iplist:
		# InfluxDB line protocol template...
		# ping,host=<host>,location=<location> rtt=<value>
		influxentry = "ping,host=" + key[0] + ",location=" + key[1][1] + ",function=" + key[1][2] + " rtt=" + str(key[1][3])
		if key[1][3] == 9999:
			#tabledata = '<td class="downred">{hostname}<br>{ipaddress}<br>DOWN!</td>'.format(hostname=key[1][0], ipaddress=key[0])
			tabledata = '<td class="downred"><a href="{influxlaunch}{ipaddress}" target="_blank">{hostname}</a><br>{ipaddress}<br>DOWN!</td>'.format(influxlaunch=influxlaunch, hostname=key[1][0], ipaddress=key[0])
		elif float(key[1][3]) > warningratio:
			tabledata = '<td class="warnyellow"><a href="{influxlaunch}{ipaddress}" target="_blank">{hostname}</a><br>{ipaddress}<br>{rtt} ms</td>'.format(influxlaunch=influxlaunch, hostname=key[1][0], ipaddress=key[0], rtt=key[1][3])
		else:
			tabledata = '<td class="upgreen"><a href="{influxlaunch}{ipaddress}" target="_blank">{hostname}</a><br>{ipaddress}<br>{rtt} ms</td>'.format(influxlaunch=influxlaunch, hostname=key[1][0], ipaddress=key[0], rtt=key[1][3])
		influxdata.append(influxentry)
		
		if columncount == htmlcolumncount:
			html = '\n'.join([html, '</tr>\n<tr>'])
			columncount = 0
		else:
			html = '\n'.join([html, tabledata])
		columncount += 1
	
	influxdata = '\n'.join(influxdata)
	
	fh = open(dashboardfilename, "w")
	fh.write('\n'.join([html, endtable, "<p>Last Run:", timenow, "</p>", "</body>"]))
	fh.close()
	return influxdata

def write2influx():
	influxdata = createtabledata()
	url = "http://localhost:8086/write"
	params = {"db":databasename}
	headers = {
    	'Content-Type': "application/x-www-form-urlencoded",
    	}
	
	response = requests.request("POST", url, data=influxdata, headers=headers, params=params)
	#print(response.text)
	
def dowork():
	timenow = datetime.datetime.fromtimestamp(time.time()).strftime('%Y-%m-%d %H:%M:%S')
	print("I'm working...", timenow)
	write2influx()
	timenow = datetime.datetime.fromtimestamp(time.time()).strftime('%Y-%m-%d %H:%M:%S')
	print("I'm done...", timenow)
	
schedule.every(15).seconds.do(dowork)

while 1:
	schedule.run_pending()
	time.sleep(1)	