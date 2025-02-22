#!/usr/bin/env python
# -*- coding: utf-8 -*-

from django.conf import settings
from django.utils import six
from django.utils.six.moves.urllib.parse import parse_qsl, urlencode, urlparse
from django import template
from djangoseo.seo import get_metadata, get_linked_metadata
from django.template import VariableDoesNotExist
import os

register = template.Library()


class MetadataNode(template.Node):
    def __init__(self, metadata_name, variable_name, target, site, language, subdomain):
        self.metadata_name = metadata_name
        self.variable_name = variable_name
        self.target = template.Variable(target or 'request.path')
        self.site = site and template.Variable(site) or None
        self.language = language and template.Variable(language) or None
        self.subdomain = template.Variable(subdomain or 'request.subdomain')

    def render(self, context):
        try:
            target = self.target.resolve(context)
        except VariableDoesNotExist:
            msg = ("{% get_metadata %} needs some path information.\n"
                        "Please use RequestContext with the django.core.context_processors.request context processor.\n"
                        "Or provide a path or object explicitly, eg {% get_metadata for path %} or {% get_metadata for object %}")
            raise template.TemplateSyntaxError(msg)
        else:
            if callable(target):
                target = target()
            if isinstance(target, six.string_types):
                # path = target
                # inspect the string target for querystring if found: sort the keys of the query string and set to path
                # else: set path = target
                # NOTE 1.11 This is code to enable query string matching it is not in the orignal repo
                # it requires the context_processor for current_path
                # here context.get('current_path') should be:
                # u'/search/?departments=accessories&sort=popular&style=hat&type=cuffed-knit-beanie'
                # and target should be:
                # u'/search/'
                path = context.get('current_path', target)
                parsed = urlparse(path)
                if settings.APPEND_SLASH:
                    if parsed[2]:
                        new_path = os.path.join(parsed[2], '', '')
                        parsed = parsed._replace(path=new_path)
                if parsed[4]:
                    query_string = parse_qsl(parsed[4])
                    sorted_qs = sorted(query_string, key=lambda tup: tup[0])
                    new_qs = urlencode(sorted_qs, 'utf-8')
                    parsed = parsed._replace(query=new_qs)
                    path = parsed.geturl()

            elif hasattr(target, 'get_absolute_url'):
                path = target.get_absolute_url()
            elif hasattr(target, "__iter__") and 'get_absolute_url' in target:
                path = target['get_absolute_url']()
            else:
                path = None

        kwargs = {}

        # If a site is given, pass that on
        if self.site:
            kwargs['site'] = self.site.resolve(context)

        # If a language is given, pass that on
        if self.language:
            kwargs['language'] = self.language.resolve(context)

        # If a subdomain is given, pass that on
        if self.subdomain:
            try:
                kwargs['subdomain'] = self.subdomain.resolve(context)
            except VariableDoesNotExist:
                pass

        metadata = None
        # If the target is a django model object
        if hasattr(target, 'pk'):
            metadata = get_linked_metadata(target, self.metadata_name, context, **kwargs)
        if not isinstance(path, six.string_types):
            path = None
        if not metadata:
            # Fetch the metadata
            try:
                metadata = get_metadata(path, self.metadata_name, context, **kwargs)
            except Exception as e:
                raise template.TemplateSyntaxError(e)

        # If a variable name is given, store the result there
        if self.variable_name is not None:
            context.dicts[0][self.variable_name] = metadata
            return ""
        else:
            return six.text_type(metadata)


def do_get_metadata(parser, token):
    """
    Retrieve an object which can produce (and format) metadata.

        {% get_metadata [for my_path] [in my_language] [on my_site] [as my_variable] %}

        or if you have multiple metadata classes:

        {% get_metadata MyClass [for my_path] [in my_language] [on my_site] [as my_variable] %}

    """
    bits = list(token.split_contents())
    tag_name = bits[0]
    bits = bits[1:]
    metadata_name = None
    args = {'as': None, 'for': None, 'in': None, 'on': None, 'under': None}

    # If there are an even number of bits,
    # a metadata name has been provided.
    if len(bits) % 2:
        metadata_name = bits[0]
        bits = bits[1:]

    # Each bits are in the form "key value key value ..."
    # Valid keys are given in the 'args' dict above.
    while len(bits):
        if len(bits) < 2 or bits[0] not in args:
            raise template.TemplateSyntaxError("expected format is '%r [as <variable_name>]'" % tag_name)
        key, value, bits = bits[0], bits[1], bits[2:]
        args[key] = value

    return MetadataNode(
        metadata_name,
        variable_name=args['as'],
        target=args['for'],
        site=args['on'],
        language=args['in'],
        subdomain=args['under']
    )


register.tag('get_metadata', do_get_metadata)
