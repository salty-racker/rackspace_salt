# -*- coding: utf-8 -*-
"""
Module to provide Rackspace infrastructure compatibility to Salt.

:depends: pyrax Rackspace python SDK
:configuration:
    The following values are required to be present in pillar for this module to work::
        rackspace:
            username: USERNAME
            apikey: API_KEY

    The various functions generally follow the following format:
        driver_type_action
        dns_record_list
        dns_zone_create
"""

# Import Python libs
import json
import six
import logging

logger = logging.getLogger(__name__)

# Import salt libs
import salt.utils

#Import pyrax
HAS_PYRAX = False
try:
    import pyrax
    import pyrax.exceptions as exc
    from pyrax import clouddatabases, clouddns, cloudloadbalancers, cloudblockstorage, cloudmonitoring, cloudnetworks, cloudfiles
    HAS_PYRAX = True
    pyrax.set_setting("identity_type", "rackspace")
except ImportError:
    logger.error("Could not import Pyrax")
    pass

#TODO: Add Absent Modules
#TODO: Add Get Modules

#Global variables that aren't available from pyrax
MAX_DB_VOLUME_SIZE = 150
MINIMUM_TTL = 300
PAGE_SIZE = 100

#DNS
VALID_RECORD_TYPES = ['A', 'AAAA', 'CNAME', 'MX' 'NS', 'PTR', 'SRV', 'TXT']
PRIORITY_RECORD_TYPES = ["MX", 'SRV']


def __virtual__():
    """
    Only load if pyrax is available
    """
    if not HAS_PYRAX:
        return False
    return "rackspace"


### CLOUD SERVERS
def cs_images_list():
    """
    Generated a list of all cloud server images in the default region
    :return: A list of image names
    """
    driver = _get_driver('cs')
    output = []
    for image in driver.flavors.list():
        output.append(image.name)
    return {'images': output}


###CLOUD LBS
def lb_list():
    """
    Generates a list of dicts of all load balancers in a given region
    :return: A dict keyed by name of the LB
    """
    driver = _get_driver('lb')
    output = {}
    for lb in driver.list():
        out = {lb.name: {'port': lb.port, 'status': lb.status}}
        output.update(out)
    return output


### CLOUD DNS
def dns_zone_list(show_records=False):
    """
    Generate a list of all DNS Domains on this account
    :param show_records: Boolean if the listed zones should display all of their records
    :return:
    """
    driver = _get_driver('dns')
    assert isinstance(driver, clouddns.CloudDNSClient)
    output = []
    for zone in _dns_zone_list():
        output.append(_dns_zone_to_dict(zone, show_records))
    return output


def dns_zone_create(name, emailAddress, ttl=False):
    """
    Crease the specified DNS zone
    :param name: Name of the DNS zone
    :param emailAddress: Email address to associate with the zone
    :param ttl: Default ttl value for all records on the zone
    :return: A dict representation of the created zone
    """
    driver = _get_driver('dns')
    assert isinstance(driver, clouddns.CloudDNSClient)

    if not ttl:
        dom = driver.create(name=name, emailAddress=emailAddress)
    else:
        dom = driver.create(name=name, emailAddress=emailAddress, ttl=ttl)
    return _dns_zone_to_dict(dom)


def dns_zone_exists(name, **kwargs):
    """
    Determines if a dns Zone exists
    :param name: Name of the dns zone
    :param kwargs:
    :return:
    """
    try:
        zone = _dns_zone_get_by_name(name)
    except exc.NotFound:
        return False

    emailAddress = kwargs.get('emailAddress', zone.emailAddress)
    ttl = kwargs.get('ttl', zone.ttl)

    if zone.ttl != ttl or zone.emailAddress != emailAddress:
        return False

    return True


def dns_zone_update(name, **kwargs):
    """
    Updates a dns zone based on the provided kwargs
    :param name: The name of the zone
    :param kwargs: emailAddress, ttl
    :return: A dict of the updated zone
    """
    zone = _dns_zone_get_by_name(name)
    assert isinstance(zone, clouddns.CloudDNSDomain)

    field_types = ['emailAddress', 'ttl']

    if not set(field_types).intersection(set(kwargs)):
        raise TypeError("Must provide one of the following: {}".format(field_types))

    comment = kwargs.get('comment', '')
    emailAddress = kwargs.get('emailAddress', zone.emailAddress)
    ttl = kwargs.get('ttl', zone.ttl)

    if ttl < MINIMUM_TTL:
        raise ValueError('ttl has a minimum value of {}'.format(MINIMUM_TTL))

    zone.update(emailAddress=emailAddress, ttl=ttl, comment=comment)
    zone.reload()
    return _dns_zone_to_dict(zone)


def dns_zone_get(name, show_records=False):
    """
    Retrieves a specific DNS zone by name
    :param name: The name of the zone
    :return: A dict of the zone.
    """

    zone = _dns_zone_get_by_name(name)
    assert isinstance(zone, clouddns.CloudDNSDomain)
    return _dns_zone_to_dict(zone, show_records=show_records)


def dns_zone_delete(name, delete_subdomains=False):
    """
    Removes specified dns zone
    :param name: The name of the zone
    :param delete_subdomains: Determines if subdomains should be deleted
    :return: A Dict with all the names of a zones dealt with
    """
    driver = _get_driver('dns')
    assert isinstance(driver, clouddns.CloudDNSClient)

    try:
        zone = _dns_zone_get_by_name(name)
    except exc.NotFound:
        raise
    assert isinstance(zone, clouddns.CloudDNSDomain)

    output = {}

    if delete_subdomains:
        for subdomain in driver.get_subdomain_iterator(zone):
            sub_name = subdomain.name
            subdomain.delete()
            output[sub_name] = True

    zone.delete()
    output[name] = True

    return output


def dns_record_list(zone_name):
    """
    Returns a list of Records for the given DNS zone.
    :param zone_name: A str/unicode object that represents the zone's name Ex. example.com
    :return: A list of all records based on the zone name.
    """
    zone = _dns_zone_get_by_name(zone_name)
    all_records = _dns_record_list(zone)
    output = []
    for record in all_records:
        output.append(_dns_record_to_dict(record))
    return output


def dns_record_create(zone_name, record_name, record_type, data, ttl=False, priority=None, comment=False):
    """
    Creates the specified record.
    :param zone_name: A str/unicode object that represents the zone's name Ex. example.com
    :param record_name: A str/unicode object that represents the record's name. Ex subdomain.example.com
    :param record_type: A sty/unicode object of a valid records type. Ex. A AAAA CNAME etc
    :param data: A str/unicode object that is the data associated with the record. Ex. "127.0.0.1"
    :param ttl: An integer  that represents the records ttl
    :param priority: An integer that represents the MX/SRV priority
    :param comment: A str/unicode object for the comment on the record
    :return: A dict of the created record
    """
    driver = _get_driver('dns')
    assert isinstance(driver, clouddns.CloudDNSClient)

    if not _is_valid_record_type(record_type):
        raise TypeError(u"Not a valid record type: {}".format(record_type))

    record_dict = {
        'type': record_type,
        'name': record_name,
        'data': data,
    }

    if ttl:
        record_dict['ttl'] = ttl

    if comment:
        record_dict['comment'] = comment

    #looking for records valid for use with priority
    if record_type in PRIORITY_RECORD_TYPES:
        if priority is None:
            raise ValueError("priority required for MX records")
        else:
            record_dict['priority'] = priority

    dom = _dns_zone_get_by_name(name=zone_name)
    recs = dom.add_records([record_dict])
    return [_dns_record_to_dict(record) for record in recs]


def dns_record_exists(zone_name, record_name, record_type, data, ttl=False, priority=False):
    """
    Determines if a DNS Record exists on this account.
    :param zone_name: A str/unicode object that represents the zone's name Ex. example.com
    :param record_name: A str/unicode object that represents the record's name. Ex subdomain.example.com
    :param record_type: A sty/unicode object of a valid records type. Ex. A AAAA CNAME etc
    :param data: A str/unicode object that is the data associated with the record. Ex. "127.0.0.1"
    :param ttl: An integer  that represents the records ttl
    :param priority: An integer that represents the MX/SRV priority
    :return: True/False if the specified record is found.
    """
    try:
        records = _dns_records_get_by_name(zone_name, record_name, record_type, data=data)
    except exc.NotFound:
        return False

    #comparing specific values for records since we can only search by type, name and data
    for record in records:
        found = True
        if ttl:
            if record.ttl != ttl:
                found = False

        if priority:
            if record_type in PRIORITY_RECORD_TYPES:
                if record.priority != priority:
                    found = False
            else:
                logger.warning(u'Record type does not use priority: {}'.format(record_type))

        if found:
            return True

    return False


def dns_record_update(zone_name, record_name, record_type, data, ttl=False, priority=False, comment=''):
    """
    Updates a record that matches the specified zone and record type
    :param zone_name: A str/unicode object that represents the zone's name Ex. example.com
    :param record_name: A str/unicode object that represents the record's name. Ex subdomain.example.com
    :param record_type: A sty/unicode object of a valid records type. Ex. A AAAA CNAME etc
    :param data: A str/unicode object that is the data associated with the record. Ex. "127.0.0.1"
    :param ttl: An integer  that represents the records ttl
    :param priority: An integer that represents the MX/SRV priority
    :param comment: A str/unicode object for the comment on the record
    :return: A dict of the now updated record
    """
    record = _dns_records_get_by_name(zone_name, record_name, record_type, allow_multiple_records=False)[0]
    assert isinstance(record, clouddns.CloudDNSRecord)

    record.update(data=data, priority=priority, ttl=ttl, comment=comment)
    return _dns_record_to_dict(record)


def _dns_records_get_by_name(zone_name, record_name, record_type, data=None, allow_multiple_records=True):
    """
    Finds a record based on the record name
    :param zone_name: A str/unicode object that represents the zone's name Ex. example.com
    :param record_name: A str/unicode object that represents the record's name. Ex subdomain.example.com
    :param record_type: A sty/unicode object of a valid records type. Ex. A AAAA CNAME etc
    :param data: A str/unicode object that is the data associated with the record. Ex. "127.0.0.1"
    :param allow_multiple_records: Boolean that determines if multiple records should occur with the same record name
     and type
    :return: A list of DNS Record objects that match the specified names, type and data
    """
    try:
        zone = _dns_zone_get_by_name(zone_name)
        assert isinstance(zone, clouddns.CloudDNSDomain)
    except exc.NotFound as e:
        error_msg = u"Zone Not Found: {}".format(zone_name)
        logger.error(error_msg)
        raise e

    #Checking if the record is of valid type
    if not _is_valid_record_type(record_type):
        error_msg = u"Not Valid Record Type: {}".format(record_type)
        logger.error(error_msg)
        raise TypeError(error_msg)
    record_type = record_type.upper()

    if allow_multiple_records:
        records = zone.search_records(record_type, name=record_name, data=data)
    else:
        try:
            records = [zone.find_record(record_type, name=record_name, data=data)]
        except exc.DomainRecordNotUnique:
            logger.warning(u'Multiple records found for {}: {}: {}'.format(record_name, record_type, data))
            raise
    return records


def _dns_zone_get_by_name(name):
    """
    Returns a DNS Domain object matching the specified name.
    :param name: A Str/unicode object of the zone name.
    :return: Returns a DNS Domain object matching the specified name.
    """
    driver = _get_driver('dns')
    assert isinstance(driver, clouddns.CloudDNSClient)

    dom = None
    try:
        dom = driver.find(name=name)
    except exc.NotFound:
        logger.error("No Zone found for {}".format(name))
        raise
    return dom


def _dns_record_list(zone):
    """
    Returns a list of DNS Record objects for the specified zone
    :param zone: A pyrax DNS Domain object
    :return: A list of DNS Record objects
    """
    driver = _get_driver('dns')
    assert isinstance(driver, clouddns.CloudDNSClient)
    all_records = list(driver.get_record_iterator(zone))

    return all_records


def _dns_zone_list():
    """
    Returns a list of all domains for the configured account
    :return: A list of DNS Domain objects
    """
    driver = _get_driver('dns')
    assert isinstance(driver, clouddns.CloudDNSClient)
    all_zones = driver.list(limit=PAGE_SIZE)
    while True:
        try:
            all_zones += driver.list_next_page()
        except exc.NoMoreResults:
            break
    return all_zones


def _dns_zone_to_dict(zone, show_records=False):
    """
    Renders a DNS Zone as a dict
    :param zone: A pyrax DNS Domain object
    :param show_records: Boolean to determine if records of the zone should be included in ouput
    :return: A dict
    """
    output = {
        'name': zone.name,
        'nameservers': [ns['name'] for ns in zone.nameservers],
        'id': zone.id,
        'email': zone.emailAddress,
        'ttl': zone.ttl,
    }

    if show_records:
        output['records'] = [_dns_record_to_dict(record) for record in _dns_record_list(zone)]

    return output


def _dns_record_to_dict(record):
    """
    Renders a DNS record object as a dict
    :param record: A pyrax DNS record object
    :return: A DNS record rendered as a dict. Keyed by the record name.
    """
    assert isinstance(record, clouddns.CloudDNSRecord)
    output = {'name': record.name, 'data': record.data, 'type': record.type, 'ttl': record.ttl, 'id': record.id}
    return output


##Cloud Databases
def db_flavor_list():
    """
    Retrieves a list of all current available flavors
    :return: A dict of database flavors keyed by their name.
    """
    driver = _get_driver('db')
    assert isinstance(driver, pyrax.CloudDatabaseClient)

    output = []

    for flavor in driver.list_flavors():
        output.append(_db_flavor_to_dict(flavor))
    return output


def db_flavor_exists(name):
    """
    Determines if a DB flavor of the given name exists.
    :param name: Name of the database flavor
    :return: True/False if the instance already exists
    """
    #TODO: Fix exists as we are now using lists of dictionaries instead of one big dictionary.
    flavor_dict = db_flavor_list()

    for item in flavor_dict:
        if item['name'] == name:
            return True
    return False


def db_instance_list():
    """
    Retrieves a list of rackspace cloud database instances
    :return: Dict of db instances
    """
    driver = _get_driver('db')
    assert isinstance(driver, pyrax.CloudDatabaseClient)

    output = []

    for instance in driver.list():
        output.append(_db_instance_to_dict(instance))
    return output


def db_instance_exists(name):
    """
    Determines if a DB instance of the given name is already present.
    :param name: Name of the database instance
    :return: True/False if the instance already exists
    """
    #TODO: Fix exists as we are now using lists of dictionaries instead of one big dictionary.
    for instance in db_instance_list():
        if instance['name'] == name:
            return True
    return False


def db_instance_create(name, flavor, size):
    """
    Creates a rackspace database instance
    :param name: The intended name for the database instance
    :param flavor: The name of the database flavor
    :param size: The size in GB of the database instance
    :return: A dict of the created database instance :raise ValueError:
    """
    driver = _get_driver('db')
    assert isinstance(driver, pyrax.CloudDatabaseClient)

    if db_instance_exists(name):
        raise ValueError(u"Instance Already Exists")

    if size > MAX_DB_VOLUME_SIZE:
        raise ValueError(u"Volume size must be less than 150")

    if not db_flavor_exists(flavor):
        raise ValueError(u"Invalid Flavor")

    instance = driver.create(name, flavor=_db_flavor_get_by_name(flavor), volume=size)

    return _db_instance_to_dict(instance)


def _db_instance_to_dict(instance):
    """
    Converts a database instance object to a dict
    :param instance: A valid pyrax instance object
    :return: A dict representation of the instance keyed by the instance name
    """
    assert isinstance(instance, clouddatabases.CloudDatabaseInstance)
    return {
        'name': instance.name,
        'id': instance.id,
        'status': instance.status,
        'flavor': instance.flavor.name,
        'hostname': instance.hostname
    }


def _db_flavor_get_by_name(name):
    """
    Retrieves a database flavor object by name
    :param name: A str/unicode object of the flavor name
    :return: A pyrax flavor object
    :raise ValueError: If no valid flavors are found
    """
    driver = _get_driver('db')
    assert isinstance(driver, pyrax.CloudDatabaseClient)
    flavor_list = driver.list_flavors()

    for flavor in flavor_list:
        if flavor.name == name:
            return flavor

    raise ValueError(u"No Flavor by that name")


def _db_flavor_to_dict(flavor):
    """
    Converts a flavor object to a dict
    :param flavor: A valid pyrax flavor object
    :return: A dict representation of the flavor keyed by the flavor name
    """
    assert isinstance(flavor, clouddatabases.CloudDatabaseFlavor)
    return {'name': flavor.name, 'ram': flavor.ram, 'id': flavor.id}


def _is_valid_record_type(record_type):
    """
    Checks to see if record_type is a valid str/unicode object and if it is a valid type of record.
        Example types of records:
           'A', 'AAAA', 'CNAME', 'MX' 'NS', 'PTR', 'SRV', 'TXT'

    :param record_type: A str or unicode object matching one of the above types of records
    :return: True/False If it is a valid record type
    :raise TypeError: If records_type is not a valid str or unicode object
    """
    if not isinstance(record_type, six.string_types):
        raise TypeError(u"record_type must be str or unicode object")

    if record_type.upper() in VALID_RECORD_TYPES:
        return True

    return False


#### Utility Functions
def _auth():
    """
    Authenticates against the rackspace api
    """
    rackspace = __salt__['config.get']('rackspace')
    username = rackspace['username']
    apikey = rackspace['apikey']
    try:
        pyrax.set_credentials(username, apikey)
    except exc.AuthenticationFailed:
        logger.error(
            u"Unable to authenticate with the provided credentials, {}, {}, {}".format(username, apikey, rackspace)
        )


def _get_driver(driver_type, region='DFW'):
    """
    Returns the appropriate diver for the specified rackspace product.

    Available options include::
        lb: Cloud Load Balancers
        db: Cloud Databases
        dns: Cloud DNS
        bs: Cloud Block Storage
        mon: Cloud Monitoring
        net: Cloud Networks
        cf: Cloud Files
        cs: Cloud Servers

    :param driver_type: A str or unicode object for the appropriate type of driver above.
    :param region: A str or unicode object specify which region the driver should be initialized for.
    :return: A driver object initialized to the specified region
    :raise TypeError:
    :raise KeyError: If no valid drivers are found
    """
    _auth()
    if not isinstance(driver_type, six.string_types):
        raise TypeError("driver_type must be str or unicode object")
    if not isinstance(region, six.string_types):
        raise TypeError("region must be str or unicode object")
    region = region.upper()

    if driver_type == "lb":
        return pyrax.connect_to_cloud_loadbalancers(region)

    if driver_type == "db":
        return pyrax.connect_to_cloud_databases(region)

    if driver_type == "dns":
        return pyrax.connect_to_cloud_dns()

    if driver_type == "bs":
        return pyrax.connect_to_cloud_blockstorage(region)

    if driver_type == "mon":
        return pyrax.connect_to_cloud_monitoring(region)

    if driver_type == "net":
        return pyrax.connect_to_cloud_networks(region)

    if driver_type == 'cf':
        return pyrax.connect_to_cloudfiles(region)

    if driver_type == 'cs':
        return pyrax.connect_to_cloudservers(region)

    raise KeyError(u"No Driver found by: {}".format(driver_type))


def _get_endpoints(service_name):
    _auth()
    if service_name in pyrax.services:
        return pyrax.services[service_name]["endpoints"].keys()
    else:
        error_msg = u'No service found: {}'.format(service_name)
        logger.error(error_msg)
        raise TypeError(error_msg)


def _check_region(service_name, region):
    #TODO: needs to be plugged in
    # for svc in pyrax.services:
    # print svc, pyrax.identity.services[svc]["endpoints"].keys()
    #
    # load_balancer [u'DFW', u'ORD', u'SYD']
    # compute [u'DFW', u'ORD', u'SYD']
    # monitor ['ALL']
    # database [u'ORD', u'DFW', u'SYD']
    # object_cdn [u'ORD', u'DFW', u'SYD']
    # volume [u'DFW', u'ORD', u'SYD']
    # dns ['ALL']
    # autoscale [u'ORD', u'DFW']
    # backup ['ALL']
    # object_store [u'DFW', u'ORD', u'SYD']
    service_names = {
        'lb': 'load_balancer',
        'cs': 'compute',
        'mon': 'monitor',
        'db': 'database',
        'cf': 'object_store',
        'bs': 'volume',
        'dns': 'dns',

    }

    region = region.upper()
    regions = _get_endpoints(service_name)

    if len(regions) == 1:
        if regions[0].upper() == 'ALL':
            return True

    if region in regions:
        return True

    return False