import copy
import difflib
import re
import urllib
import urlparse

import pycountry
import pymarc
from PyZ3950 import zoom

from django.conf import settings
from django.db import connection
from django.utils.encoding import smart_str, DjangoUnicodeDecodeError

from ui import apis
from ui import marc
from ui import z3950
from ui.templatetags.launchpad_extras import cjk_info
from ui.templatetags.launchpad_extras import clean_isbn
from ui.templatetags.launchpad_extras import clean_lccn
from ui.templatetags.launchpad_extras import clean_oclc
from django.utils.encoding import iri_to_uri
from django.utils.http import urlquote

# = = =  = = = = = = = = = = = = = = = = = = = = = = = = = 
# This is a shortened version of voyager.py 
# specific to the subject heading search / browse feature
# = = =  = = = = = = = = = = = = = = = = = = = = = = = = = 

def _make_dict(cursor, first=False):
    desc = cursor.description
    mapped = [
        dict(zip([col[0] for col in desc], row))
        for row in cursor.fetchall()
    ]
    # strip string values of trailing whitespace
    for d in mapped:
        for k, v in d.items():
            try:
                d[k] = smart_str(v.strip())
            except:
                pass
    if first:
        if len(mapped) > 0:
            return mapped[0]
        return {}
    return mapped

# may need this at some point
def fix_ampersands(qs):
    """
    Try to fix openurl that don't encode ampersands correctly. This is kind of
    tricky business. The basic idea is to split the query string on '=' and
    then inpsect each part to make sure there aren't more than one '&'
    characters in it. If there are, all but the last are assumed to need
    encoding. Similarly, if an ampersand is present in the last part, it
    is assumed to need encoding since there is no '=' following it.

    TODO: if possible we should really try to fix wherever these OpenURLs are
    getting created upstream instead of hacking around it here.
    """
    parts = []
    for p in qs.split('='):
        if p.count('&') > 1:
            l = p.split('&')
            last = l.pop()
            p = '%26'.join(l) + '&' + last
        parts.append(p)

    # an & in the last part definitely needs encoding
    parts[-1] = parts[-1].replace('&', '%26')

    return '='.join(parts)

def get_heading_id(norm_inputstring):
    # The norm_inputstring is a normalized, uppercase version of the subject heading
    query = """
    SELECT HEADING_ID FROM heading WHERE normal_heading='"""
    query +=  norm_inputstring + """' AND HEADING_TYPE='lcsh'"""
    cursor = connection.cursor()
    cursor.execute(query)
    result = _make_dict(cursor)
    return result[0]['HEADING_ID']

def get_headings_list(headingID):
    startID = str(headingID)
    endID   = int(headingID) + 100
    query ="""
    SELECT DISTINCT 
    HEADING_VW.OPACBIBS, HEADING_VW.HEADING_ID, HEADING_VW.NORMAL_HEADING, HEADING_VW.DISPLAY_HEADING, 
    HEADING_VW.HEADING_TYPE, HEADING_VW.INDEX_NAME 
    FROM HEADING_VW 
    WHERE HEADING_VW.OPACBIBS > '0' AND HEADING_VW.INDEX_NAME = 'Subject' 
    AND HEADING_VW.HEADING_ID Between '"""  + startID + """' and '"""  + str(endID) + """'
    ORDER BY HEADING_VW.HEADING_ID """
    cursor = connection.cursor()
    cursor.execute(query)
    headings = _make_dict(cursor)
    # Confirmed this query gets desired results
    # TODO:    Return results to the page for display
    return headings

def get_titles_for_heading(headingID,options):
    # TODO: BULLET-PROOF. Assuming four options
    query ="""
    SELECT 
    heading.HEADING_ID, heading.display_heading, heading.normal_heading, 
    BIB_HEADING.BIB_ID, 
    BIB_MASTER.LIBRARY_ID, 
    LIBRARY.LIBRARY_NAME, 
    BIB_TEXT.TITLE, BIB_TEXT.AUTHOR, BIB_TEXT.BIB_FORMAT, BIB_TEXT.IMPRINT, 
    BIB_TEXT.ISBN, BIB_TEXT.ISSN,BIB_TEXT.BEGIN_PUB_DATE
    FROM heading INNER JOIN BIB_HEADING ON heading.HEADING_ID = BIB_HEADING.HEADING_ID 
    INNER JOIN BIB_MASTER ON BIB_HEADING.BIB_ID = BIB_MASTER.BIB_ID 
    INNER JOIN LIBRARY ON BIB_MASTER.LIBRARY_ID = LIBRARY.LIBRARY_ID 
    INNER JOIN BIB_TEXT ON BIB_MASTER.BIB_ID = BIB_TEXT.BIB_ID
    WHERE 
    heading.HEADING_ID='""" + str(headingID) + """' 
    AND heading.index_type='S' 
    AND BIB_MASTER.SUPPRESS_IN_OPAC='N'"""
    if not 'all' in options[1]:
        if 'GW'  in options[1]:
            query += """ AND LIBRARY.LIBRARY_NAME in ('GW','E-Resources','E-GovDoc','JB') """
        if 'GW' not in options[1]:
            query += """ AND LIBRARY.LIBRARY_NAME ='""" + options[1] + """' """
    if 'title' in options[0]:
        query += """ ORDER BY BIB_TEXT.TITLE_BRIEF, BIB_TEXT.ISBN, BIB_TEXT.ISSN, LIBRARY.LIBRARY_NAME""" 
    else:
        query += """ ORDER BY BIB_TEXT.BEGIN_PUB_DATE DESC, BIB_TEXT.TITLE_BRIEF"""
    cursor = connection.cursor()
    cursor.execute(query)
    result = _make_dict(cursor)
    return result


