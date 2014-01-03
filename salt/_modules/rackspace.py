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
    output = []
    for lb in clb.list():
        out = {lb.name: {'port': lb.port, 'status': lb.status}}
    output.append(out)
    return output


### CLOUD DNS
def dns_domain_list():
    driver = _get_driver('dns')
    assert isinstance(driver, clouddns.CloudDNSClient)

    output = {}

    #Get first page of domains
    for domain in driver.list():
        output[domain.name] = _domain_to_dict(domain)

    #Rest of domains
    while True:
        try:
            for domain in driver.list_next_page():
                output[domain.name] = _domain_to_dict(domain)
        except exc.NoMoreResults:
            break

    return output


def dns_domain_create(name, emailAddress, ttl=False, comment=""):
    driver = _get_driver('dns')
    assert isinstance(driver, clouddns.CloudDNSClient)
    logger.error(u'{}, {}, {}, {}'.format(name, emailAddress, ttl, comment))
    if not ttl:
        dom = driver.create(name=name, emailAddress=emailAddress)
    else:
        dom = driver.create(name=name, emailAddress=emailAddress, ttl=ttl)
    return _domain_to_dict(dom)


def dns_record_list(name):
    domain = _get_domain_by_name(name)

    return _dns_record_list(domain)


def dns_record_create(name, record_type, data, ttl=600, priority=None, comment=""):
    driver = _get_driver('dns')
    assert isinstance(driver, clouddns.CloudDNSClient)

    rec = {
        'type': record_type,
        'name': name,
        'data': data,
        'comment': comment,
        'ttl': ttl
    }

    if record_type == "MX":
        if priority is None:
            raise ValueError("priority required for MX records")
        else:
            rec['priority'] = priority

    dom = _get_domain_by_name(name=name)
    recs = dom.add_records([rec])
    return [_dns_record_to_dict(record) for record in recs]


def dns_domain_exists(name, **kwargs):
    try:
        domain = _get_domain_by_name(name)
    except exc.NotFound:
        return False

    emailAddress = kwargs.get('emailAddress', domain.emailAddress)
    ttl = kwargs.get('ttl', domain.ttl)

    if domain.ttl != ttl or domain.emailAddress != emailAddress:
        return False

    return True


def dns_domain_update(name, **kwargs):
    #TODO: Allow nameservers
    domain = _get_domain_by_name(name)
    assert isinstance(domain, clouddns.CloudDNSDomain)

    field_types = ['emailAddress', 'ttl']

    if not set(field_types).intersection(set(kwargs)):
        raise TypeError("Must provide one of the following: {}".format(field_types))

    comment = kwargs.get('comment', '')
    emailAddress = kwargs.get('emailAddress', domain.emailAddress)
    ttl = kwargs.get('ttl', domain.ttl)

    if ttl < MINIMUM_TTL:
        raise ValueError('ttl has a minimum value of {}'.format(MINIMUM_TTL))

    domain.update(emailAddress=emailAddress, ttl=ttl, comment=comment)
    domain.reload()
    return _domain_to_dict(domain)


def _get_domain_by_name(name):
    driver = _get_driver('dns')
    assert isinstance(driver, clouddns.CloudDNSClient)

    dom = None
    try:
        dom = driver.find(name=name)
    except exc.NotFound:
        logger.error("No Domain found for {}".format(name))
        raise

    #if dom_list) > 1:
    #    #TODO: Determine how to deal with multi match
    #    logger.error("Multiple Matching domains")
    #    raise LookupError("Multiple Matching Domains")
    return dom


def _dns_record_list(domain):
    output = {}
    offset = 0
    #Get first page of domains
    for record in domain.list_records(limit=PAGE_SIZE):
        output.update(_dns_record_to_dict(record))

    #TODO: fix paging
    #Rest of domains
    #while True:
    #    offset += PAGE_SIZE
    #    try:
    #        for record in domain.list_records(limit=PAGE_SIZE, offset=offset):
    #            output[record.name] = _dns_record_to_dict(record)
        #
    #    except exc.NoMoreResults:
    #        break

    return output


def _domain_to_dict(domain):
    output = {
        'nameservers': [ns['name'] for ns in domain.nameservers],
        'id': domain.id,
        'email': domain.emailAddress,
        'ttl': domain.ttl,
        'records': [_dns_record_list(domain)]
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
        raise ValueError("Instance Already Exists")

    if size > MAX_DB_VOLUME_SIZE:
        raise ValueError("Volume size must be less than 150")

    if not db_flavor_exists(flavor):
        raise ValueError("Invalid Flavor")

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

    raise ValueError("No Flavor by that name")


def _db_flavor_to_dict(flavor):
    assert isinstance(flavor, clouddatabases.CloudDatabaseFlavor)
    return {flavor.name: {
        'ram': flavor.ram,
        'id': flavor.id,
    }
    }


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
            "Unable to authenticate with the provided credentials, {}, {}, {}".format(username, apikey, rackspace))


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