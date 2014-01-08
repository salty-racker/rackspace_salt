# -*- coding: utf-8 -*-
"""
Module to provide Rackspace infastructure compatibility to Salt.

:depends: pyrax Rackspace python SDK
:configuration:
    The following values are required to be present in pillar for this module to work::
        rackspace:
            username: USERNAME
            apikey: API_KEY
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
    from pyrax import clouddatabases, clouddns, cloudloadbalancers, cloudblockstorage, cloudmonitoring, cloudnetworks

    HAS_PYRAX = True
    pyrax.set_setting("identity_type", "rackspace")
except ImportError:
    logger.error("Could not import Pyrax")
    pass


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
def list_images():
    _auth()
    cs = pyrax.cloudservers
    output = []
    for image in cs.flavors.list():
        output.append(image.name)
    return {'load_balancers': output}


###CLOUD LBS
def list_lbs():
    _auth()
    clb = pyrax.cloud_loadbalancers
    output = {}
    for lb in clb.list():
        out = {lb.name: {'port': lb.port, 'status': lb.status}}
        output.update(out)
    return output


### CLOUD DNS
def dns_zone_list():
    driver = _get_driver('dns')
    assert isinstance(driver, clouddns.CloudDNSClient)

    output = {}

    #Get first page of zones
    for zone in driver.list():
        output[zone.name] = _dns_zone_to_dict(zone)

    #Rest of zones
    while True:
        try:
            for zone in driver.list_next_page():
                output[zone.name] = _dns_zone_to_dict(zone)
        except exc.NoMoreResults:
            break

    return output


def dns_zone_create(name, emailAddress, ttl=False, comment=""):
    driver = _get_driver('dns')
    assert isinstance(driver, clouddns.CloudDNSClient)

    if not ttl:
        dom = driver.create(name=name, emailAddress=emailAddress)
    else:
        dom = driver.create(name=name, emailAddress=emailAddress, ttl=ttl)
    return _dns_zone_to_dict(dom)


def dns_zone_exists(name, **kwargs):
    try:
        zone = _get_zone_by_name(name)
    except exc.NotFound:
        return False

    emailAddress = kwargs.get('emailAddress', zone.emailAddress)
    ttl = kwargs.get('ttl', zone.ttl)

    if zone.ttl != ttl or zone.emailAddress != emailAddress:
        return False

    return True


def dns_zone_update(name, **kwargs):
    #TODO: Allow nameservers
    zone = _get_zone_by_name(name)
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


def dns_record_list(zone_name):
    zone = _get_zone_by_name(zone_name)
    all_records = _dns_record_list(zone)
    output = {}

    for record in all_records:
        output.update(_dns_record_to_dict(record))

    return output


def dns_record_create(zone_name, record_name, record_type, data, ttl=False, priority=None, comment=False):
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

    dom = _get_zone_by_name(name=zone_name)
    recs = dom.add_records([record_dict])
    return [_dns_record_to_dict(record) for record in recs]


def dns_record_exists(zone_name, record_name, record_type, data, ttl=False, priority=False):
    try:
        records = _get_records_by_name(zone_name, record_name, record_type, data=data)
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

    record = _get_records_by_name(zone_name, record_name, record_type, allow_multiple_records=False)[0]
    assert isinstance(record, clouddns.CloudDNSRecord)

    record.update(data=data, priority=priority, ttl=ttl, comment=comment)
    return _dns_record_to_dict(record)


def _get_records_by_name(zone_name, record_name, record_type, data=None, allow_multiple_records=True):
    try:
        zone = _get_zone_by_name(zone_name)
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
        logger.debug(u'{} {} {}'.format(record_type, record_name, data))
        records = zone.search_records(record_type, name=record_name, data=data)
    else:
        records = [zone.find_record(record_type, name=record_name, data=data)]
    return records


def _get_zone_by_name(name):
    driver = _get_driver('dns')
    assert isinstance(driver, clouddns.CloudDNSClient)

    dom = None
    try:
        dom = driver.find(name=name)
    except exc.NotFound:
        logger.error("No Zone found for {}".format(name))
        raise

    #if dom_list) > 1:
    #    #TODO: Determine how to deal with multi match
    #    logger.error("Multiple Matching domains")
    #    raise LookupError("Multiple Matching Domains")
    return dom


def _dns_record_list(zone):
    driver = _get_driver('dns')
    all_records = list(driver.get_record_iterator(zone))

    return all_records


def _dns_zone_to_dict(zone):
    output = {
        'nameservers': [ns['name'] for ns in zone.nameservers],
        'id': zone.id,
        'email': zone.emailAddress,
        'ttl': zone.ttl,
        'records': [_dns_record_to_dict(record) for record in _dns_record_list(zone)]
    }
    return output


def _dns_record_to_dict(record):
    assert isinstance(record, clouddns.CloudDNSRecord)
    output = {record.name: {'data': record.data, 'type': record.type, 'ttl': record.ttl, 'id': record.id}}
    return output


##Cloud Databases
def db_flavor_list():
    driver = _get_driver('db')
    assert isinstance(driver, pyrax.CloudDatabaseClient)

    output = {}

    for flavor in driver.list_flavors():
        output.update(_db_flavor_to_dict(flavor))
    return output


def db_flavor_exists(name):
    flavor_dict = db_flavor_list()
    return name in flavor_dict


def db_instance_list():
    """
    Retrieves a list of rackspace cloud database instances
    :return: Dict of db instances
    """
    driver = _get_driver('db')
    assert isinstance(driver, pyrax.CloudDatabaseClient)

    output = {}

    for instance in driver.list():
        output.update(_db_instance_to_dict(instance))
    return output


def db_instance_exists(name):
    instance_dict = db_instance_list()
    return name in instance_dict


def db_instance_create(name, flavor, size):
    driver = _get_driver('db')
    assert isinstance(driver, pyrax.CloudDatabaseClient)

    if db_flavor_exists(name):
        raise ValueError(u"Instance Already Exists")

    if size > MAX_DB_VOLUME_SIZE:
        raise ValueError(u"Volume size must be less than 150")

    if not db_flavor_exists(flavor):
        raise ValueError(u"Invalid Flavor")

    instance = driver.create(name, flavor=_db_flavor_get_by_name(flavor), volume=size)

    return _db_instance_to_dict(instance)


def _db_instance_to_dict(instance):
    assert isinstance(instance, clouddatabases.CloudDatabaseInstance)
    return {instance.name: {
        'id': instance.id,
        'status': instance.status,
        'flavor': instance.flavor.name,
        'hostname': instance.hostname
    }
    }


def _db_flavor_get_by_name(name):
    driver = _get_driver('db')
    assert isinstance(driver, pyrax.CloudDatabaseClient)
    flavor_list = driver.list_flavors()

    for flavor in flavor_list:
        if flavor.name == name:
            return flavor

    raise ValueError(u"No Flavor by that name")


def _db_flavor_to_dict(flavor):
    assert isinstance(flavor, clouddatabases.CloudDatabaseFlavor)
    return {flavor.name: {'ram': flavor.ram, 'id': flavor.id}}


def _is_valid_record_type(record_type):
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


def _get_driver(driver_type):
    """
    Returns the appropriate diver for the specified rackspace product.

    Available options include::
        lb: Cloud Load Balancers
        db: Cloud Databases
        dns: Cloud DNS

    :param driver_type:
    :return: :raise TypeError:
    """
    #TODO: Add region support
    _auth()
    if not isinstance(driver_type, six.string_types):
        raise TypeError("driver_type must be str or unicode object")

    if driver_type == "lb":
        return pyrax.cloud_loadbalancers

    if driver_type == "db":
        return pyrax.cloud_databases

    if driver_type == "dns":
        return pyrax.cloud_dns

    #TODO: Add rest of drivers

    raise KeyError("No Driver found by: {}".format(driver_type))