import xml.etree.cElementTree as ElementTree
from collections import defaultdict
import re
import pprint

# Audit street names -> fix suffixes
# Some street names include suite/apartment numbers (e.g. 2B, Suite 500)
# Some street names are intersections "x and y", "x & y" or "x between y"
# Some street names are duplicated "abc; xyz"

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
                return "%s%s" % (street_name_prefix, self._canonical_suffix_map[street_type])


class StreetNameAvenueXCleaner(object):
    _ALPHABET_AVE_RE = re.compile('^Avenue ([A-Z])$', re.IGNORECASE)

    def clean(self, street_name):
        m = self._ALPHABET_AVE_RE.search(street_name)
        if m:
            letter = m.group(1)
            return 'Avenue %s' % letter


def audit_street_type(street_types, street_name, cleaners):
    for cleaner in cleaners:
        res = cleaner.clean(street_name)
        if res is not None:
            print("[%s] => [%s]" % (street_name, res))
            return

    m = STREET_TYPE_RE.search(street_name)
    if m:
        street_type = m.group(2)
        street_types[street_type].add(street_name)


def is_street_name(elem):
    return elem.attrib['k'] == 'addr:street'


def audit(osmfile):
    street_name_cleaners = [StreetNameCanonicalSuffixCleaner(), StreetNameAvenueXCleaner()]

    osm_file = open(osmfile, 'r')
    street_types = defaultdict(set)
    for event, elem in ElementTree.iterparse(osm_file, events=('start',)):

        if elem.tag == 'node' or elem.tag == 'way':
            for tag in elem.iter('tag'):
                if is_street_name(tag):
                    audit_street_type(street_types, tag.attrib['v'], street_name_cleaners)

    return street_types


def update_name(name, mapping):
    m = STREET_TYPE_RE.search(name)
    if m:
        street_name = m.group(1)
        street_type = m.group(2)
        if street_type in mapping:
            name = street_name + mapping[street_type]

    return name


if __name__ == '__main__':
    st_types = audit('new-york_new-york.osm')
    print("")
    print("")
    print("Unclassified streets:")
    pprint.pprint(dict(st_types))

    # for st_type, ways in st_types.iteritems():
    # for name in ways:
    # better_name = update_name(name, mapping)
    #         print name, "=>", better_name
