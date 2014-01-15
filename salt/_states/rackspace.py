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
import logging

logger = logging.getLogger(__name__)

# Import salt libs
import salt.utils

#Import pyrax
HAS_PYRAX = False
try:
    import pyrax
    import pyrax.exceptions as exc

    HAS_PYRAX = True
    pyrax.set_setting("identity_type", "rackspace")
except ImportError:
    logger.error("Could not import Pyrax")
    pass


def __virtual__():
    """
    Only load if pyrax is availible and has the correct values in pillar
    """
    if not HAS_PYRAX:
        return False
    return "rackspace"


def db_instance_exists(name, flavor, size, opts=False):
    ret = {'name': name, 'result': True, 'comment': '', 'changes': {}}

    does_exist = __salt__['rackspace.db_instance_exists'](name)

    if not does_exist:
        if __opts__['test']:
            ret['result'] = None
            ret['comment'] = u'DB instance {0} set to be created'.format(name)
            return ret
        try:
            created = __salt__['rackspace.db_instance_create'](name, flavor, size)
            ret['changes']['new'] = created
        except ValueError as e:
            ret['result'] = False
            ret['comment'] = u'Unable to create: {}'.format(e.message)

    else:
        ret['comment'] = u'{0} exists'.format(name)

    return ret


def dns_zone_exists(name, emailAddress=None, ttl=None, opts=False):
    ret = {'name': name, 'result': True, 'comment': '', 'changes': {}}

    does_exist = __salt__['rackspace.dns_zone_exists'](name, emailAddress=emailAddress, ttl=ttl)

    if not does_exist:
        if __opts__['test']:
            ret['result'] = None
            ret['comment'] = u'DNS Zone {0} set to be created'.format(name)
            return ret

        base_zone_exists = __salt__['rackspace.dns_zone_exists'](name)
        if not base_zone_exists:
            created = __salt__['rackspace.dns_zone_create'](name, emailAddress=emailAddress, ttl=ttl)
            ret['changes']['new'] = created
        else:
            updated = __salt__['rackspace.dns_zone_update'](name, emailAddress=emailAddress, ttl=ttl)
            ret['changes']['updated'] = updated
    else:
        ret['comment'] = u'{0} exists'.format(name)

    return ret


def dns_record_exists(name, zone_name, record_type, data, ttl=None, priority=None, comment=None, allow_multiple_records=False, opts=False):
    ret = {'name': name, 'result': True, 'comment': '', 'changes': {}}

    does_exist = __salt__['rackspace.dns_record_exists'](zone_name, name, record_type, data=data, ttl=ttl,
                                                         priority=priority)
    if not does_exist:
        if __opts__['test']:
            ret['result'] = None
            ret['comment'] = u'DNS Record for {0} set to be created/updated'.format(name)
            return ret


        #passing none for data as we are only concerned with finding a record of the same type
        base_record_exists = __salt__['rackspace.dns_record_exists'](zone_name, name, record_type, data=None)

        if not base_record_exists:
            created = __salt__['rackspace.dns_record_create'](zone_name, name, record_type, data, ttl=600,
                                                              priority=priority, comment=comment)
            ret['changes']['new'] = created

        else:
            #TODO: Deal with overlapping FQDN with A, AAAA and CNAME
            #We've found there is a base record
            #Checking to see if we need to update or add another
            #We are choosing to update if only the TTL or Priority are different
            needs_updating = __salt__['rackspace.dns_record_exists'](zone_name, name, record_type, data=data)
            if needs_updating:
                updated = __salt__['rackspace.dns_record_update'](
                    zone_name, name, record_type, data, ttl=ttl, priority=priority, comment=comment
                )
                ret['changes']['updated'] = updated

            #If this is not the case we check for allow multiple records
            elif allow_multiple_records:

                #if multiple records are allowed we create a "new" record with the same record type
                created = __salt__['rackspace.dns_record_create'](
                    zone_name, name, record_type, data, ttl=600, priority=priority, comment=comment
                )
                ret['changes']['new'] = created

            #if they are not we are updating the old with the new data
            else:
                updated = __salt__['rackspace.dns_record_update'](
                    zone_name, name, record_type, data, ttl=ttl, priority=priority, comment=comment
                )
                ret['changes']['updated'] = updated
    else:
        ret['comment'] = u'{0} exists'.format(name)

    return ret