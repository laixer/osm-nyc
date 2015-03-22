import xml.etree.cElementTree as ElementTree
from collections import defaultdict
import re
import pprint

# Audit street names -> fix suffixes
# Some street names include suite/apartment numbers (e.g. 2B, Suite 500)
# Some street names are intersections "x and y", "x & y" or "x between y"
# Some street names are duplicated "abc; xyz"

street_type_re = re.compile(r'^(.*?)\b(\S+\.?)$', re.IGNORECASE)

ALPHABET_AVE_RE = re.compile('^Avenue [A-Z]$')

STEET_SUFFIX_ALTERNATIVES = {
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


def build_street_canonical_suffix_map():
    """
    Builds a map of street suffixes to their canonical representations.
    """
    canonical_suffix_map = {}
    for canonical_suffix, alternative_suffixes in STEET_SUFFIX_ALTERNATIVES.iteritems():
        # Map canonical suffix to itself for convenience.
        canonical_suffix_map[canonical_suffix] = canonical_suffix
        for alternative_suffix in alternative_suffixes:
            canonical_suffix_map[alternative_suffix] = canonical_suffix
    return canonical_suffix_map


def audit_street_type(street_types, street_name, street_canonical_suffix_map):
    # Ignore letter avenues in Manhattan/Brooklyn.
    if ALPHABET_AVE_RE.search(street_name):
        return

    m = street_type_re.search(street_name)
    if m:
        street_type = m.group(2)
        if street_type not in street_canonical_suffix_map:
            street_types[street_type].add(street_name)


def is_street_name(elem):
    return elem.attrib['k'] == 'addr:street'


def audit(osmfile):
    street_canonical_suffix_map = build_street_canonical_suffix_map()
    osm_file = open(osmfile, 'r')
    street_types = defaultdict(set)
    for event, elem in ElementTree.iterparse(osm_file, events=('start',)):

        if elem.tag == 'node' or elem.tag == 'way':
            for tag in elem.iter('tag'):
                if is_street_name(tag):
                    audit_street_type(street_types, tag.attrib['v'], street_canonical_suffix_map)

    return street_types


def update_name(name, mapping):
    m = street_type_re.search(name)
    if m:
        street_name = m.group(1)
        street_type = m.group(2)
        if street_type in mapping:
            name = street_name + mapping[street_type]

    return name


if __name__ == '__main__':
    st_types = audit('new-york_new-york.osm')
    pprint.pprint(dict(st_types))

    # for st_type, ways in st_types.iteritems():
    # for name in ways:
    # better_name = update_name(name, mapping)
    #         print name, "=>", better_name
