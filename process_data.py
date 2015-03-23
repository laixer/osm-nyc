import xml.etree.cElementTree as ElementTree
from collections import defaultdict
import re
import pprint
import codecs
import json

# Audit street names -> fix suffixes
# Some street names include suite/apartment numbers (e.g. 2B, Suite 500)
# Some street names are intersections "x and y", "x & y" or "x between y"
# Some street names are duplicated "abc; xyz"

lower = re.compile(r'^([a-z]|_)*$')
lower_colon = re.compile(r'^([a-z]|_)*:([a-z]|_)*$')
problemchars = re.compile(r'[=\+/&<>;\'"\?%#$@\,\. \t\r\n]')

CREATED = ['version', "changeset", 'timestamp', 'user', 'uid']

STREET_TYPE_RE = re.compile(r'^(.*?)\b(\S+\.?)$', re.IGNORECASE)


class StreetNameCanonicalSuffixCleaner(object):
    _STREET_SUFFIX_ALTERNATIVES = {
        'Alley': {},
        'Americas': {},  # Avenue of the Americas
        'Avenue': {'AVE.', 'AVENUE', 'Ave', 'Ave,', 'Ave.', 'Avenue,', 'ave', 'avenue', 'Avene', 'Aveneu'},
        'Boulevard': {'Blv.', 'Blvd', 'Blvd.', 'boulevard'},
        'Broadway': {},
        'Center': {},
        'Circle': {'Cir', 'CIRCLE'},
        'Concourse': {},
        'Court': {'Ct', 'Ct.'},
        'Crescent': {},
        'Drive': {'DRIVE', 'Dr', 'Dr.', 'drive'},
        'East': {'EAST'},
        'Expressway': {},
        'Extension': {},
        'Finest': {},  # Avenue of the finest
        'Heights': {},
        'Highway': {'Hwy'},
        'Lane': {'LANE'},
        'Loop': {},
        'North': {'north'},
        'Park': {},
        'Parkway': {'Pkwy', 'Pky', 'PARKWAY'},
        'Place': {'Pl', 'PLACE'},
        'Plaza': {'Plz', 'PLAZA'},
        'Road': {'ROAD', 'Rd', 'road'},
        'Square': {},
        'South': {},
        'Street': {'St', 'St.', 'Steet', 'Street', 'st', 'street', 'STREET', 'ST'},
        'Terrace': {},
        'Turnpike': {'Tpke'},
        'Walk': {},
        'West': {'WEST'},
        'Way': {'WAY'},
    }

    def build_street_canonical_suffix_map(self):
        """
        Builds a map of street suffixes to their canonical representations.
        """
        canonical_suffix_map = {}
        for canonical_suffix, alternative_suffixes in self._STREET_SUFFIX_ALTERNATIVES.iteritems():
            # Map canonical suffix to itself for convenience.
            canonical_suffix_map[canonical_suffix] = canonical_suffix
            for alternative_suffix in alternative_suffixes:
                canonical_suffix_map[alternative_suffix] = canonical_suffix
        return canonical_suffix_map

    def __init__(self):
        self._canonical_suffix_map = self.build_street_canonical_suffix_map()

    def clean(self, street_name):
        m = STREET_TYPE_RE.search(street_name)
        if m:
            street_name_prefix = m.group(1)
            street_type = m.group(2)
            if street_type in self._canonical_suffix_map:
                return '%s%s' % (street_name_prefix, self._canonical_suffix_map[street_type])


class StreetNameAvenueXCleaner(object):
    _ALPHABET_AVE_RE = re.compile('^Avenue ([A-Z])$', re.IGNORECASE)

    def clean(self, street_name):
        m = self._ALPHABET_AVE_RE.search(street_name)
        if m:
            letter = m.group(1)
            return 'Avenue %s' % letter


def clean_street_type(street_types, street_name, cleaners):
    for cleaner in cleaners:
        res = cleaner.clean(street_name)
        if res is not None:
            print('[%s] => [%s]' % (street_name, res))
            return res

    m = STREET_TYPE_RE.search(street_name)
    if m:
        street_type = m.group(2)
        street_types[street_type].add(street_name)
    return street_name


def process_map(file_in, pretty=False):
    street_types = defaultdict(set)
    street_name_cleaners = [StreetNameCanonicalSuffixCleaner(), StreetNameAvenueXCleaner()]
    file_out = '{0}.json'.format(file_in)
    with codecs.open(file_out, 'w') as fo:
        for _, element in ElementTree.iterparse(file_in):
            el = shape_element(element)
            if el:
                if "address" in el and "street" in el["address"]:
                    el["address"]["street"] = clean_street_type(
                        street_types, el["address"]["street"], street_name_cleaners)
                if pretty:
                    fo.write(json.dumps(el, indent=2) + '\n')
                else:
                    fo.write(json.dumps(el) + '\n')
    print('')
    print('')
    print('Unclassified streets:')
    pprint.pprint(dict(street_types))


def shape_element(element):
    node = {}
    if element.tag == 'node' or element.tag == 'way':
        node['type'] = element.tag
        node['created'] = {}
        for k, v in element.attrib.iteritems():
            if k in CREATED:
                node['created'][k] = v
            elif k != 'lat' and k != 'lon':
                node[k] = v
        if 'lat' in element.attrib and 'lon' in element.attrib:
            node['pos'] = [float(element.attrib['lat']), float(element.attrib['lon'])]
        for el in element.iter('tag'):
            k = el.attrib['k']
            v = el.attrib['v']
            if not problemchars.search(k):
                if k.startswith('addr:'):
                    if 'address' not in node:
                        node['address'] = {}
                    nk = k[5:]
                    if ':' not in nk:
                        node['address'][nk] = v
        for el in element.iter('nd'):
            if 'node_refs' not in node:
                node['node_refs'] = []
            node['node_refs'].append(el.attrib['ref'])
        return node
    else:
        return None


if __name__ == '__main__':
    process_map('new-york_new-york.osm')
