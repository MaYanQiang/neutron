# Copyright 2012 VMware, Inc.
# All rights reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import abc

from neutron_lib.api import converters
from neutron_lib.api import extensions
from neutron_lib.db import constants as db_const
from neutron_lib import exceptions as nexception
import six

from neutron._i18n import _
from neutron.api.v2 import resource_helper
from neutron.conf import quota
from neutron.plugins.common import constants


# L3 Exceptions
class RouterNotFound(nexception.NotFound):
    message = _("Router %(router_id)s could not be found")


class RouterInUse(nexception.InUse):
    message = _("Router %(router_id)s %(reason)s")

    def __init__(self, **kwargs):
        if 'reason' not in kwargs:
            kwargs['reason'] = "still has ports"
        super(RouterInUse, self).__init__(**kwargs)


class RouterInterfaceNotFound(nexception.NotFound):
    message = _("Router %(router_id)s does not have "
                "an interface with id %(port_id)s")


class RouterInterfaceNotFoundForSubnet(nexception.NotFound):
    message = _("Router %(router_id)s has no interface "
                "on subnet %(subnet_id)s")


class RouterInterfaceInUseByFloatingIP(nexception.InUse):
    message = _("Router interface for subnet %(subnet_id)s on router "
                "%(router_id)s cannot be deleted, as it is required "
                "by one or more floating IPs.")


class FloatingIPNotFound(nexception.NotFound):
    message = _("Floating IP %(floatingip_id)s could not be found")


class ExternalGatewayForFloatingIPNotFound(nexception.NotFound):
    message = _("External network %(external_network_id)s is not reachable "
                "from subnet %(subnet_id)s.  Therefore, cannot associate "
                "Port %(port_id)s with a Floating IP.")


class FloatingIPPortAlreadyAssociated(nexception.InUse):
    message = _("Cannot associate floating IP %(floating_ip_address)s "
                "(%(fip_id)s) with port %(port_id)s "
                "using fixed IP %(fixed_ip)s, as that fixed IP already "
                "has a floating IP on external network %(net_id)s.")


class RouterExternalGatewayInUseByFloatingIp(nexception.InUse):
    message = _("Gateway cannot be updated for router %(router_id)s, since a "
                "gateway to external network %(net_id)s is required by one or "
                "more floating IPs.")


class RouterInterfaceAttachmentConflict(nexception.Conflict):
    message = _("Error %(reason)s while attempting the operation.")


ROUTERS = 'routers'
FLOATINGIP = 'floatingip'
FLOATINGIPS = '%ss' % FLOATINGIP
EXTERNAL_GW_INFO = 'external_gateway_info'

RESOURCE_ATTRIBUTE_MAP = {
    ROUTERS: {
        'id': {'allow_post': False, 'allow_put': False,
               'validate': {'type:uuid': None},
               'is_visible': True,
               'primary_key': True},
        'name': {'allow_post': True, 'allow_put': True,
                 'validate': {'type:string': db_const.NAME_FIELD_SIZE},
                 'is_visible': True, 'default': ''},
        'admin_state_up': {'allow_post': True, 'allow_put': True,
                           'default': True,
                           'convert_to': converters.convert_to_boolean,
                           'is_visible': True},
        'status': {'allow_post': False, 'allow_put': False,
                   'is_visible': True},
        'tenant_id': {'allow_post': True, 'allow_put': False,
                      'required_by_policy': True,
                      'validate': {
                          'type:string': db_const.PROJECT_ID_FIELD_SIZE},
                      'is_visible': True},
        EXTERNAL_GW_INFO: {'allow_post': True, 'allow_put': True,
                           'is_visible': True, 'default': None,
                           'enforce_policy': True,
                           'validate': {
                               'type:dict_or_nodata': {
                                   'network_id': {'type:uuid': None,
                                                  'required': True},
                                   'external_fixed_ips': {
                                       'convert_list_to':
                                       converters.convert_kvp_list_to_dict,
                                       'type:fixed_ips': None,
                                       'default': None,
                                       'required': False,
                                   }
                               }
                           }}
    },
    FLOATINGIPS: {
        'id': {'allow_post': False, 'allow_put': False,
               'validate': {'type:uuid': None},
               'is_visible': True,
               'primary_key': True},
        'floating_ip_address': {'allow_post': True, 'allow_put': False,
                                'validate': {'type:ip_address_or_none': None},
                                'is_visible': True, 'default': None,
                                'enforce_policy': True},
        'subnet_id': {'allow_post': True, 'allow_put': False,
                      'validate': {'type:uuid_or_none': None},
                      'is_visible': False,  # Use False for input only attr
                      'default': None},
        'floating_network_id': {'allow_post': True, 'allow_put': False,
                                'validate': {'type:uuid': None},
                                'is_visible': True},
        'router_id': {'allow_post': False, 'allow_put': False,
                      'validate': {'type:uuid_or_none': None},
                      'is_visible': True, 'default': None},
        'port_id': {'allow_post': True, 'allow_put': True,
                    'validate': {'type:uuid_or_none': None},
                    'is_visible': True, 'default': None,
                    'required_by_policy': True},
        'fixed_ip_address': {'allow_post': True, 'allow_put': True,
                             'validate': {'type:ip_address_or_none': None},
                             'is_visible': True, 'default': None},
        'tenant_id': {'allow_post': True, 'allow_put': False,
                      'required_by_policy': True,
                      'validate': {
                          'type:string': db_const.PROJECT_ID_FIELD_SIZE},
                      'is_visible': True},
        'status': {'allow_post': False, 'allow_put': False,
                   'is_visible': True},
    },
}

# Register the configuration options
quota.register_quota_opts(quota.l3_quota_opts)


class L3(extensions.ExtensionDescriptor):

    @classmethod
    def get_name(cls):
        return "Neutron L3 Router"

    @classmethod
    def get_alias(cls):
        return "router"

    @classmethod
    def get_description(cls):
        return ("Router abstraction for basic L3 forwarding"
                " between L2 Neutron networks and access to external"
                " networks via a NAT gateway.")

    @classmethod
    def get_updated(cls):
        return "2012-07-20T10:00:00-00:00"

    @classmethod
    def get_resources(cls):
        """Returns Ext Resources."""
        plural_mappings = resource_helper.build_plural_mappings(
            {}, RESOURCE_ATTRIBUTE_MAP)
        action_map = {'router': {'add_router_interface': 'PUT',
                                 'remove_router_interface': 'PUT'}}
        return resource_helper.build_resource_info(plural_mappings,
                                                   RESOURCE_ATTRIBUTE_MAP,
                                                   constants.L3_ROUTER_NAT,
                                                   action_map=action_map,
                                                   register_quota=True)

    def update_attributes_map(self, attributes):
        super(L3, self).update_attributes_map(
            attributes, extension_attrs_map=RESOURCE_ATTRIBUTE_MAP)

    def get_extended_resources(self, version):
        if version == "2.0":
            return RESOURCE_ATTRIBUTE_MAP
        else:
            return {}


@six.add_metaclass(abc.ABCMeta)
class RouterPluginBase(object):

    @abc.abstractmethod
    def create_router(self, context, router):
        pass

    @abc.abstractmethod
    def update_router(self, context, id, router):
        pass

    @abc.abstractmethod
    def get_router(self, context, id, fields=None):
        pass

    @abc.abstractmethod
    def delete_router(self, context, id):
        pass

    @abc.abstractmethod
    def get_routers(self, context, filters=None, fields=None,
                    sorts=None, limit=None, marker=None, page_reverse=False):
        pass

    @abc.abstractmethod
    def add_router_interface(self, context, router_id, interface_info):
        pass

    @abc.abstractmethod
    def remove_router_interface(self, context, router_id, interface_info):
        pass

    @abc.abstractmethod
    def create_floatingip(self, context, floatingip):
        pass

    @abc.abstractmethod
    def update_floatingip(self, context, id, floatingip):
        pass

    @abc.abstractmethod
    def get_floatingip(self, context, id, fields=None):
        pass

    @abc.abstractmethod
    def delete_floatingip(self, context, id):
        pass

    @abc.abstractmethod
    def get_floatingips(self, context, filters=None, fields=None,
                        sorts=None, limit=None, marker=None,
                        page_reverse=False):
        pass

    def get_routers_count(self, context, filters=None):
        raise NotImplementedError()

    def get_floatingips_count(self, context, filters=None):
        raise NotImplementedError()
