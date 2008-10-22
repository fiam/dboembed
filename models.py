# -*- coding: utf-8 -*-

# This file is part of dboembed
# Copyright (c) 2008 Alberto García Hierro <fiam@rm-fr.net>

# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:

# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.

# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.

from datetime import datetime
from urllib2 import urlopen, quote, URLError
from httplib import InvalidURL
from xml.etree.cElementTree import iterparse
import re

from django.db import models
from django.utils.translation import ugettext_lazy
from django.utils.safestring import mark_safe

class oEmbeddingProvider(object):
    def __init__(self, name, scheme, endpoint):
        self.name = name
        self.re = re.compile(scheme, re.I|re.U)
        self.endpoint = endpoint

    def match(self, url):
        return self.re.match(url)

    def request_url(self, url, maxwidth=None, maxheight=None):
        m = self.re.match(url)
        if m:
            rurl = self.endpoint + u'url=%s' % quote(url.encode('utf8'))
            if maxwidth:
                rurl += u'&maxwidth=%s' % maxwidth
            if maxheight:
                rurl += u'&maxheight=%s' % maxheight

            return rurl
        return None

OEMBEDDING_PROVIDERS = [
    oEmbeddingProvider(name='Flickr',
        scheme='http://(.*?\.)?flickr\.com/.*',
        endpoint='http://www.flickr.com/services/oembed/?format=xml&'),
    oEmbeddingProvider(name='Viddler',
        scheme='http://(.*?\.)?viddler\.com/.*',
        endpoint='http://lab.viddler.com/services/oembed/?format=xml&'),
    oEmbeddingProvider(name='Qik',
        scheme='http://qik\.com/video/.*',
        endpoint='http://qik.com/api/oembed.xml?'),
    oEmbeddingProvider(name='Pownce',
        scheme='http://(.*?\.)?pownce\.com/.*',
        endpoint='http://api.pownce.com/2.1/oembed.xml?'),
    oEmbeddingProvider(name='Revision3',
        scheme='http://(.*?\.)?revision3\.com/.*',
        endpoint='http://revision3\.com/api/oembed/?format=xml&'),
    oEmbeddingProvider(name='Hulu',
        scheme='http://www\.hulu\.com/watch/.*',
        endpoint='http://www.hulu.com/api/oembed.xml?'),
    oEmbeddingProvider(name='Vimeo',
        scheme='http://www.vimeo.com/.*',
        endpoint='http://www.vimeo.com/api/oembed.xml?'),
]

class oEmbedProvider(models.Model):
    MAX_URL_LENGTH = 512
    MAX_NAME_LENGTH = 64
    provider_name = models.CharField(max_length=MAX_NAME_LENGTH, null=True, db_index=True)
    provider_url = models.CharField(max_length=MAX_URL_LENGTH, null=True)

    def __unicode__(self):
        return u'%s, %s' % (self.provider_name, self.provider_url)

class oEmbed(models.Model):
    MAX_URL_LENGTH = 512
    MAX_NAME_LENGTH = 64
    OEMBED_TYPES = (
        ('P', ugettext_lazy('photo')),
        ('V', ugettext_lazy('video')),
        ('L', ugettext_lazy('link')),
        ('R', ugettext_lazy('rich')),
    )
    TYPE_MAPPING = {
        'photo': 'P',
        'video': 'V',
        'link': 'L',
        'rich': 'R',
    }
    MANDATORY_FIELDS = {
        'P': set(['url', 'width', 'height' ]),
        'V': set(['html', 'width', 'height' ]),
        'L': set([]),
        'rich': set(['html', 'width', 'height' ]),
    }
    PROVIDER_FIELDS = set(['provider_name', 'provider_url'])
    OEMBED_FIELDS = set(['title', 'author_name', 'author_url', \
                    'thumbnail_url', 'thumbnail_width', 'thumbnail_height', \
                    'url', 'width', 'height', 'html', 'cache_age'])

    type = models.CharField(max_length=1, choices=OEMBED_TYPES)
    title = models.CharField(max_length=MAX_NAME_LENGTH, null=True)
    author_name = models.CharField(max_length=MAX_NAME_LENGTH, null=True)
    author_url = models.CharField(max_length=MAX_URL_LENGTH, null=True)
    provider = models.ForeignKey(oEmbedProvider, null=True)
    thumbnail_url = models.CharField(max_length=MAX_URL_LENGTH, null=True)
    thumbnail_width = models.IntegerField(null=True)
    thumbnail_height = models.IntegerField(null=True)
    url = models.CharField(max_length=MAX_URL_LENGTH, null=True)
    width = models.IntegerField(null=True)
    height = models.IntegerField(null=True)
    html = models.TextField(null=True)
    cache_age = models.IntegerField(null=True)
    created = models.DateTimeField(default=datetime.now)

    def get_html(self):
        if self.html:
            return mark_safe(self.html)

        if self.type == 'P':
            return mark_safe('<img alt="%(title)s" src="%(src)s" ' \
                'width="%(width)s" height="%(height)s" />' % \
                {
                    'title': self.title or '',
                    'src': self.url,
                    'width': self.width,
                    'height': self.height,
                })

    @staticmethod
    def from_url(url, maxwidth=None, maxheight=None):
        for oep in OEMBEDDING_PROVIDERS:
            rurl = oep.request_url(url, maxwidth, maxheight)
            if rurl:
                return oEmbed.from_resource_url(rurl)

        return None

    @staticmethod
    def from_resource_url(url):
        properties = {}
        provider_properties = {}
        try:
            fp = urlopen(url)
        except (URLError, InvalidURL, ValueError):
            return None
        try:
            for event, element in iterparse(fp):
                if element.tag == 'version':
                    if element.text != '1.0':
                        raise ValueError('Invalid protocol version: "%s"' % element.text)
                elif element.tag == 'type':
                    try:
                        properties['type'] = oEmbed.TYPE_MAPPING[element.text]
                    except KeyError:
                        raise ValueError('Invalid resource type: "%s"' % element.text)
                elif element.tag in oEmbed.PROVIDER_FIELDS:
                    provider_properties[element.tag] = element.text
                elif element.tag in oEmbed.OEMBED_FIELDS:
                    properties[element.tag] = element.text
        except SyntaxError:
            return None

        try:
            if oEmbed.MANDATORY_FIELDS[properties['type']] - set(properties.keys()):
                raise ValueError('Missing fields for type %s: "%s"' % \
                    (properties['type'],
                    ','.join(str(x) for x in oEmbed.MANDATORY_FIELDS[properties['type']] - set(properties.keys()))))
        except KeyError:
            raise ValueError('Invalid type: "%s"' % properties.get('type'))

        if provider_properties:
            properties['provider'] = oEmbedProvider.objects.get_or_create(**provider_properties)[0]

        return oEmbed.objects.create(**properties)

