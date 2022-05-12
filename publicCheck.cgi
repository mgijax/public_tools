#!/usr/local/bin/python

# Name: publicCheck.cgi
# Purpose: check the health of the various pieces of the public MGI presence,
#	helping to diagnose problems and link to solutions

import sys
sys.path.insert(0, '/usr/local/mgi/live/lib/python')
import os
import re
import cgi
import pg_db
import runCommand

###--- constants ---###

DB_SERVER = 'dbServer'
MGD_DB_NAME = 'mgdDatabase'
FE_DB_NAME = 'feDatabase'
FEWI_URL = 'fewiUrl'
FEWI_BATCH_URL = 'fewiBatchUrl'
FE_SOLR_URL = 'feSolrUrl'
GXD_SOLR_URL1 = 'gxdSolrUrl1'
GXD_SOLR_URL2 = 'gxdSolrUrl2'
GXD_SOLR_URL3 = 'gxdSolrUrl3'
SNP_SOLR_URL = 'snpSolrUrl'
NIB_URL = 'nibUrl'

# colors chosen to work for people with color blindness, per:
# http://mkweb.bcgsc.ca/colorblind/img/colorblindness.palettes.trivial.png
GREEN = '#009E73'	# bluish green
YELLOW = '#F0E442'		# yellow

# regex for pulling server & port out of a URL
URL_RE = re.compile('https?://([^/]+).*')

# sample of mgd tables to check counts
MGD_TABLES = [ 'mrk_marker', 'all_allele', 'bib_refs', 'gxd_assay' ]

# sample of mgd tables to check counts
FE_TABLES = [ 'marker', 'allele', 'reference', 'expression_assay' ]

# sample of fewi pages to check
FEWI_PAGES = [ 'marker', 'marker/MGI:96677', 'marker/summary?nomen=kit' ]

# sample of indexes to check counts
FE_SOLR_INDEXES = [ 'marker', 'allele', 'reference', ] 

# sample of indexes to check counts (GXD)
GXD_SOLR_INDEXES = [ 'gxdResult', 'gxdImagePane' ]

# sample of indexes to check counts (SNPs)
SNP_SOLR_INDEXES = [ 'SearchSNPIndex', 'ConsensusSNPIndex', 'AlleleSNPIndex' ]

# canned URL for sequence retrieval from NIB files
NIB_URL = 'http://www.informatics.jax.org/seqfetch/tofasta.cgi?seq1=mousegenome%21OTTMUSG00000016671%215%2175574916%2175656722%21%2B%21&flank1=0'

###--- configuration ---###

pub1 = {
	DB_SERVER : 'bhmgipubdb01lp.jax.org',
	MGD_DB_NAME : 'pub',
	FE_DB_NAME : 'fe',
	FEWI_URL : 'http://bhmgipubweb01lp.jax.org:8080/fewi/mgi',
	FEWI_BATCH_URL : 'http://bhmgipubweb01lp.jax.org:18080/fewi/mgi',
	FE_SOLR_URL : 'http://bhmgipfesolr01lp.jax.org:9995/solr',
	GXD_SOLR_URL1 : 'http://bhmgipgxd01lp.jax.org:9995/solr',
	GXD_SOLR_URL2 : 'http://bhmgipgxd03lp.jax.org:9995/solr',
	GXD_SOLR_URL3 : 'http://bhmgipgxd05lp.jax.org:9995/solr',
	SNP_SOLR_URL : 'http://bhmgipsnp01lp.jax.org:18983/solr',
}

pub2 = {
	DB_SERVER : 'bhmgipubdb02lp.jax.org',
	MGD_DB_NAME : 'pub',
	FE_DB_NAME : 'fe',
	FEWI_URL : 'http://bhmgipubweb02lp.jax.org:8080/fewi/mgi',
	FEWI_BATCH_URL : 'http://bhmgipubweb02lp.jax.org:18080/fewi/mgi',
	FE_SOLR_URL : 'http://bhmgipfesolr02lp.jax.org:9995/solr',
	GXD_SOLR_URL1 : 'http://bhmgipgxd02lp.jax.org:9995/solr',
	GXD_SOLR_URL2 : 'http://bhmgipgxd04lp.jax.org:9995/solr',
	GXD_SOLR_URL3 : 'http://bhmgipgxd06lp.jax.org:9995/solr',
	SNP_SOLR_URL : 'http://bhmgipsnp01lp.jax.org:28983/solr',
}

###--- functions ---###

def jsCode():
	js = '''
<script type="text/javascript" SRC="http://www.informatics.jax.org/webshare/js/jquery-1.10.2.min.js"></script>
<script>
		function populate(test, server, divID) {
			$.get('%s?test=' + test + '&server=' + server, function(data) {
				$('#' + divID).html(data);
				});
		}
</script>''' % os.path.basename(sys.argv[0])
	return js

def message():
	return '''This script exercises various pieces of the public system via Ajax calls.  Once each test is
	complete, its corresponding table cell will be populated and color-coded.  <span style="background-color: %s">Green</span> cells
	are okay.  <span style="background-color: %s">Yellow</span> cells indicate a problem and will provide a Help link with
	instructions for how to remedy the situation.<P>
''' % (GREEN, YELLOW)
	
def serverPort (url):
	match = URL_RE.match(url)
	if match:
		return match.group(1)
	return url

def readURL (url):
	# Purpose: given constraints on reading from https connections in python
	#	2.7, we're just going to shell out and use curl for this
	# Returns: string returned
	# Throws: Exception if we have problems reading from 'url'
	
	stdout, stderr, statusCode = runCommand.runCommand("curl -m 10 '%s'" % url)
	if statusCode != 0:
		raise Exception('Failed to read from url (code %s)' % \
			statusCode)
	return stdout

def cellTitle(title):
	return '<b><u>%s</u></b>' % title

def wrapCell(lines, color = GREEN, link = None, linkText = None):
	#lines.insert(0, '<TD STYLE="background-color: %s; vertical-align: top">' % color)
	lines[0] = '<DIV STYLE="background-color: %s; vertical-align: top">%s' % (color, lines[0])
	if link and linkText:
		lines.append('<a href="%s" target="_blank">%s</a>' % (
			link, linkText))
	lines.append('</DIV>')
	return '<br/>'.join(lines)

def getCount(table):
	return pg_db.sql('select count(1) as ct from %s' % table, 'auto')[0]['ct']

def databaseCell(title, server, database, tables):
	pg_db.set_sqlLogin('mgd_public', 'mgdpub', server, database)

	out = [ cellTitle(title) ]
	color = GREEN
	link = None
	linkText = None

	try:
		out.append('sample row counts:')
		for table in tables:
			out.append('- %s : %d' % (table, getCount(table)))

	except Exception, e:
		out.append('Failed: %s' % str(e))
		color = YELLOW
		link = 'http://bhmgiwk01lp.jax.org/mediawiki/index.php/sw:Production_And_Public_Support#Starting/Stopping_Postgres'
		linkText = 'Help'

	return wrapCell(out, color, link, linkText)

def fewiCell(title, url, pages):
	out = [ cellTitle(title) ]
	color = GREEN
	link = None
	linkText = None

	try:
		for page in pages:
			myURL = '%s/%s' % (url, page)
			x = readURL(myURL)
			out.append('%s : %d bytes' % (page, len(x)))

	except Exception, e:
		out.append('Failed: %s (%s)' % (str(e), myURL))
		color = YELLOW
		link = 'http://bhmgiwk01lp.jax.org/mediawiki/index.php/sw:Production_And_Public_Support#Starting/Stopping_The_Fewi'
		linkText = 'Help'

	return wrapCell(out, color, link, linkText)

def solrCell(title, url, indexes, indexType):
	out = [ cellTitle(title) ]
	color = GREEN
	link = None
	linkText = None

	try:
		for index in indexes:
			myURL = '%s/%s/select?q=*%%3A*&wt=json&rows=0' % (url, index)
			x = readURL(myURL)
			results = eval(x)
			out.append('%s : %s documents' % (index,
				results['response']['numFound']))

	except Exception, e:
		out.append('Failed: %s (%s)' % (str(e), myURL))
		color = YELLOW
		if indexType == 'fe':
			link = 'http://bhmgiwk01lp.jax.org/mediawiki/index.php/sw:Production_And_Public_Support#Starting/Stopping_FE_Solr'
			linkText = 'Help'
		elif indexType == 'gxd':
			link = 'http://bhmgiwk01lp.jax.org/mediawiki/index.php/sw:Production_And_Public_Support#Starting/Stopping_GXD_Solr'
			linkText = 'Help'
		else:
			link = 'http://bhmgiwk01lp.jax.org/mediawiki/index.php/sw:Production_And_Public_Support#Starting/Stopping_SNP_Solr'
			linkText = 'Help'

	return wrapCell(out, color, link, linkText)

def nibFilesCell(title):
	out = [ cellTitle(title) ]
	color = GREEN
	link = None
	linkText = None

	try:
		x = readURL(NIB_URL)
		out.append('bytes read: %d' % len(x))

	except Exception, e:
		out.append('Failed: %s' % str(e))
		color = YELLOW
		link = 'http://bhmgiwk01lp.jax.org/mediawiki/index.php/sw:Production_And_Public_Support#Seqfetch_Nib_Files'
		linkText = 'Help'

	return wrapCell(out, color, link, linkText)

###--- main program ---###

out = [
	'<table style="border-spacing:5px">',
	'<tr><th>Pub 1</th><th>Pub 2</th><th>Shared</th></tr>',

	'<tr>',
	'<td id="cell1">fe database - Working...<script>populate("feDb", "pub1", "cell1")</script></td>',
	'<td id="cell2">fe database - Working...<script>populate("feDb", "pub2", "cell2")</script></td>',
	'<td id="cell3">NIB Files - Working...<script>populate("nibFiles", "pub1", "cell3")</script></td>',
	'</tr>',

	'<tr>',
	'<td id="cell4">fewi - Working...<script>populate("fewi", "pub1", "cell4")</script></td>',
	'<td id="cell5">fewi - Working...<script>populate("fewi", "pub2", "cell5")</script></td>',
	'<td>&nbsp;</td>',
	'</tr>',

	'<tr>',
	'<td id="cell6">fewi - Working...<script>populate("fewiBatch", "pub1", "cell6")</script></td>',
	'<td id="cell7">fewi - Working...<script>populate("fewiBatch", "pub2", "cell7")</script></td>',
	'<td>&nbsp;</td>',
	'</tr>',

	'<tr>',
	'<td id="cell8">fe Solr - Working...<script>populate("feSolr", "pub1", "cell8")</script></td>',
	'<td id="cell9">fe Solr - Working...<script>populate("feSolr", "pub2", "cell9")</script></td>',
	'<td>&nbsp;</td>',
	'</tr>',

	'<tr>',
	'<td id="cell10">gxd Solr - Working...<script>populate("gxdSolr1", "pub1", "cell10")</script></td>',
	'<td id="cell11">gxd Solr - Working...<script>populate("gxdSolr1", "pub2", "cell11")</script></td>',
	'<td>&nbsp;</td>',
	'</tr>',

	'<tr>',
	'<td id="cell12">gxd Solr - Working...<script>populate("gxdSolr2", "pub1", "cell12")</script></td>',
	'<td id="cell13">gxd Solr - Working...<script>populate("gxdSolr2", "pub2", "cell13")</script></td>',
	'<td>&nbsp;</td>',
	'</tr>',

	'<tr>',
	'<td id="cell14">gxd Solr - Working...<script>populate("gxdSolr3", "pub1", "cell14")</script></td>',
	'<td id="cell15">gxd Solr - Working...<script>populate("gxdSolr3", "pub2", "cell15")</script></td>',
	'<td>&nbsp;</td>',
	'</tr>',

	'<tr>',
	'<td id="cell16">SNP Solr - Working...<script>populate("snpSolr", "pub1", "cell16")</script></td>',
	'<td id="cell17">SNP Solr - Working...<script>populate("snpSolr", "pub2", "cell17")</script></td>',
	'<td>&nbsp;</td>',
	'</tr>',

	'</table>',
	]

form = cgi.FieldStorage()
if form.has_key('test') and form.has_key('server'):
	# populate an individual cell via Ajax

	print 'Content-type: text/html'
	print

	config = pub2
	if form['server'].value == 'pub1':
		config = pub1

	if form['test'].value == 'feDb':
		print databaseCell('Database : %s..%s' % (config[DB_SERVER],config[FE_DB_NAME]),
			config[DB_SERVER], config[FE_DB_NAME], FE_TABLES)
	elif form['test'].value == 'mgdDb':
		print databaseCell('Database : %s..%s' % (config[DB_SERVER],config[MGD_DB_NAME]),
			config[DB_SERVER], config[MGD_DB_NAME], MGD_TABLES)
	elif form['test'].value == 'fewi':
		print fewiCell('Fewi : %s' % serverPort(config[FEWI_URL]), config[FEWI_URL], FEWI_PAGES)
	elif form['test'].value == 'fewiBatch':
		print fewiCell('Fewi Batch : %s' % serverPort(config[FEWI_BATCH_URL]), config[FEWI_BATCH_URL], FEWI_PAGES)
	elif form['test'].value == 'feSolr':
		print solrCell('FE Solr : %s' % serverPort(config[FE_SOLR_URL]), config[FE_SOLR_URL], FE_SOLR_INDEXES, 'fe')
	elif form['test'].value == 'gxdSolr1':
		print solrCell('GXD Solr : %s' % serverPort(config[GXD_SOLR_URL1]), config[GXD_SOLR_URL1], GXD_SOLR_INDEXES, 'gxd')
	elif form['test'].value == 'gxdSolr2':
		print solrCell('GXD Solr : %s' % serverPort(config[GXD_SOLR_URL2]), config[GXD_SOLR_URL2], GXD_SOLR_INDEXES, 'gxd')
	elif form['test'].value == 'gxdSolr3':
		print solrCell('GXD Solr : %s' % serverPort(config[GXD_SOLR_URL3]), config[GXD_SOLR_URL3], GXD_SOLR_INDEXES, 'gxd')
	elif form['test'].value == 'snpSolr':
		print solrCell('SNP Solr : %s' % serverPort(config[SNP_SOLR_URL]), config[SNP_SOLR_URL], SNP_SOLR_INDEXES, 'snp')
	elif form['test'].value == 'nibFiles':
		print nibFilesCell('Sequence Retrieval : NIB Files')
	else:
		print 'unkown value for "test"'	
else:
	print 'Content-type: text/html'
	print
	print '<HTML><HEAD><TITLE>Public Health Check</TITLE></HEAD>'
	print '<BODY><H3>Public Health Check</H3>%s%s%s</BODY></HTML>' % (message(), jsCode(), '\n'.join(out))
