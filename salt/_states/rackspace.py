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


def dns_domain_exists(name, emailAddress=None, ttl=None, opts=False):
    ret = {'name': name, 'result': True, 'comment': '', 'changes': {}}

    does_exist = __salt__['rackspace.dns_domain_exists'](name, emailAddress=emailAddress, ttl=ttl)

    if not does_exist:
        if __opts__['test']:
            ret['result'] = None
            ret['comment'] = u'DNS Domain {0} set to be created'.format(name)
            return ret

        base_domain_exists = __salt__['rackspace.dns_domain_exists'](name)
        if not base_domain_exists:
            created = __salt__['rackspace.dns_domain_create'](name, emailAddress=emailAddress, ttl=ttl)
            ret['changes']['new'] = created
        else:
            updated = __salt__['rackspace.dns_domain_update'](name, emailAddress=emailAddress, ttl=ttl)
            ret['changes']['updated'] = updated
    else:
        ret['comment'] = u'{0} exists'.format(name)

    return ret