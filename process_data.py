import xml.etree.cElementTree as ElementTree
from collections import defaultdict, namedtuple
import csv
import re
import pprint
import codecs
import json

# Characters that may not appear in a key.
INVALID_KEY_CHARS = re.compile(r'[=\+/&<>;\'"\?%#$@\,\. \t\r\n]')

# Fields that we want to include in the 'created' sub-document.
CREATED_FIELDS = ['version', "changeset", 'timestamp', 'user', 'uid']
# OSM tags that should be included in the JSON output.
INCLUDE_TAGS = ['name', 'amenity', 'cuisine', 'shop']

# Regexp for parsing street name/type.
STREET_TYPE_RE = re.compile(r'^(.*?)\b(\S+\.?)$', re.IGNORECASE)
# Regexp for parsing zip codes (ignore any string prefix and take at most 5 digits).
ZIPCODE_RE = re.compile(r'(\D*?)(\d{5})')

ZipCodeData = namedtuple('ZipCodeData', ['city', 'state'])


class StreetNameCanonicalSuffixCleaner(object):
    """Cleaner that maps common street suffixes to their canonical representations."""
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
        'Finest': {},  # Avenue of the Finest
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
        """Builds a map of street suffixes to their canonical representations."""
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
    """Cleaner that takes care of "Avenue X" style street names found in NYC."""
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
            # TODO(laixer): Add configurable logging for updated data.
            # print('[%s] => [%s]' % (street_name, res))
            return res

    m = STREET_TYPE_RE.search(street_name)
    if m:
        street_type = m.group(2)
        street_types[street_type].add(street_name)
    return street_name


def load_zipcode_data():
    """Loads zipcode information data from zipcode.csv file and returns map keyed by zipcode."""
    zipcode_map = {}
    with open('zipcode.csv') as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            zipcode_data = ZipCodeData(city=row['city'], state=row['state'])
            zipcode_map[row['zip']] = zipcode_data
    # Zipcode CSV has state listed as NJ.
    zipcode_map['10004'] = ZipCodeData(city='New York', state='NY')
    return zipcode_map


def clean_postcode(postcode):
    return postcode.strip()


def process_map(file_in):
    """Processes given OSM file and yields parsed structures."""
    street_types = defaultdict(set)
    street_name_cleaners = [StreetNameCanonicalSuffixCleaner(), StreetNameAvenueXCleaner()]

    zipcode_map = load_zipcode_data()
    city_mismatches_by_zip = defaultdict(set)
    state_mismatches_by_zip = defaultdict(set)
    unknown_zips = set()
    doc_structure = defaultdict(set)

    for _, element in ElementTree.iterparse(file_in):
        el = shape_element(element, doc_structure)
        if el:
            if "address" in el:
                if "street" in el["address"]:
                    el["address"]["street"] = clean_street_type(
                        street_types, el["address"]["street"], street_name_cleaners)
                # Normalize state.
                # TODO(laixer): Separate state mappings.
                if "state" in el["address"]:
                    state = el["address"].get("state", None)
                    if state:
                        state = state.upper()
                        if state == 'NEW YORK':
                            state = 'NY'
                        elif state == 'NEW JERSEY':
                            state = 'NJ'
                        elif state == 'CONNECTICUT':
                            state = 'CT'
                        el["address"]["state"] = state
                # Compare zipcode/city/state information to zipcode database and report any mismatches.
                # If zipcode is present in zipcode database, replace existing information using database.
                if "postcode" in el["address"]:
                    el["address"]["postcode"] = clean_postcode(el["address"]["postcode"])
                    postcode_short = el["address"]["postcode"]
                    zipcode_m = ZIPCODE_RE.search(postcode_short)
                    if zipcode_m:
                        postcode_short = zipcode_m.group(2)
                    city = el["address"].get("city", None)
                    state = el["address"].get("state", None)
                    zipcode_data = zipcode_map.get(postcode_short, None)
                    if zipcode_data:
                        if city and city != zipcode_data.city:
                            city_mismatches_by_zip[postcode_short].add(city)
                        if state and state != zipcode_data.state:
                            state_mismatches_by_zip[postcode_short].add(state)
                        el["address"]["state"] = zipcode_data.state
                        el["address"]["city"] = zipcode_data.city
                    else:
                        unknown_zips.add(postcode_short)
            yield el

    print('')
    print('')
    print('Document structure:')
    pprint.pprint(dict(doc_structure))

    print('')
    print('')
    print('Unclassified streets:')
    pprint.pprint(dict(street_types))

    print('')
    print('')
    print('City mismatches:')
    for zipcode, mismatched_names in city_mismatches_by_zip.iteritems():
        print('%s: [%s] vs %s' % (zipcode, zipcode_map[zipcode].city, city_mismatches_by_zip[zipcode]))

    print('')
    print('')
    print('State mismatches:')
    for zipcode, mismatched_names in state_mismatches_by_zip.iteritems():
        print('%s: [%s] vs %s' % (zipcode, zipcode_map[zipcode].state, state_mismatches_by_zip[zipcode]))

    print('')
    print('')
    print('Unknown zips:')
    pprint.pprint(unknown_zips)


def shape_element(element, doc_structure):
    """Extracts information from given XML element and shapes into a standard format."""
    node = {}
    attribs = list(element.attrib.iteritems())
    doc_structure[element.tag].update(['attrib:' + kv[0] for kv in attribs])
    tags = []
    for el in element.iter('tag'):
        k = el.attrib['k']
        v = el.attrib['v']
        tags.append((k, v))
    doc_structure[element.tag].update(['tag:' + kv[0] for kv in tags])
    if element.tag == 'node' or element.tag == 'way':
        node['type'] = element.tag
        node['created'] = {}
        for k, v in attribs:
            if k in CREATED_FIELDS:
                node['created'][k] = v
            elif k != 'lat' and k != 'lon':
                node[k] = v
        if 'lat' in element.attrib and 'lon' in element.attrib:
            node['pos'] = [float(element.attrib['lat']), float(element.attrib['lon'])]
        for k, v in tags:
            if not INVALID_KEY_CHARS.search(k):
                if k in INCLUDE_TAGS:
                    node[k] = v
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


def main(in_file, out_file, dry_run=False):
    print('Processing [%s].' % in_file)
    f = None
    if not dry_run:
        print('Writing output to [%s].' % out_file)
        f = codecs.open(out_file, 'w')
    else:
        print('Running in dry_run mode.')

    try:
        it = process_map(in_file)
        for el in it:
            if f:
                f.write(json.dumps(el) + '\n')
    finally:
        if f:
            f.close()
    print('Done processing.')

if __name__ == '__main__':
    main('new-york_new-york.osm', 'new-york_new-york.json', dry_run=False)


