#!/usr/bin/python
""" PN CLI Layer3 Zero Touch Provisioning (ZTP) """

#
# This file is part of Ansible
#
# Ansible is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Ansible is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Ansible.  If not, see <http://www.gnu.org/licenses/>.
#

from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.network.netvisor.pn_netvisor import *
import ipaddress
import itertools as it


# Calculate ip address using ipaddress module for all subnets


DOCUMENTATION = """
---
module: pn_ztp_l3_links
author: 'Pluribus Networks (devops@pluribusnetworks.com)'
short_description: CLI command to configure ZTP for Layer3 fabric.
description:
    Zero Touch Provisioning (ZTP) allows you to provision new switches in your
    network automatically, without manual intervention. For layer3 fabric,
    it creates vrouters and configures vrouter interfaces (link IPs).
options:
    pn_net_address_ipv4:
      description:
        - Specify network address to be used in configuring link IPv4 address for layer3.
      required: False
      type: str
    pn_subnet_ipv4:
      description:
        - Specify subnet value to be used in configuring link IPv4 address for layer3.
      required: False
      type: str
    pn_net_address_ipv6:
      description:
        - Specify network address to be used in configuring link IPv6 address for layer3.
      required: False
      type: str
    pn_cidr_ipv6:
      description:
        - Specify CIDR value to be used in configuring link IPv6 address for layer3.
      required: False
      type: str
    pn_subnet_ipv6:
      description:
        - Specify subnet value to be used in configuring link IPv6 address for layer3.
      required: False
      type: str
    pn_spine_list:
      description:
        - Specify list of Spine hosts.
      required: False
      type: list
    pn_leaf_list:
      description:
        - Specify list of leaf hosts.
      required: False
      type: list
    pn_update_fabric_to_inband:
      description:
        - Flag to indicate if fabric network should be updated to in-band.
      required: False
      default: False
      type: bool
    pn_loopback_ip:
      description:
        - Loopback ip value for vrouters in layer3 fabric.
      required: False
      default: 109.109.109.0/24
      type: str
    pn_bfd:
      description:
        - Flag to indicate if BFD config should be added to vrouter interfaces
        in case of layer3 fabric.
      required: False
      default: False
      type: bool
    pn_bfd_min_rx:
      description:
        - Specify BFD-MIN-RX value required for adding BFD configuration
        to vrouter interfaces.
      required: False
      type: str
    pn_bfd_multiplier:
      description:
        - Specify BFD_MULTIPLIER value required for adding BFD configuration
        to vrouter interfaces.
      required: False
      type: str
    pn_stp:
      description:
        - Flag to enable STP at the end.
      required: False
      default: False
      type: bool
    pn_jumbo_frames:
      description:
        - Flag to assign mtu
      required: False
      default: False
      type: bool
"""

EXAMPLES = """
- name: Zero Touch Provisioning - Layer3 setup
  pn_ztp_l3_links:
    pn_cliusername: "{{ USERNAME }}"
    pn_clipassword: "{{ PASSWORD }}"
    pn_net_address_ipv4: '192.168.0.1'
    pn_subnet_ipv4: '30'
"""

RETURN = """
summary:
  description: It contains output of each configuration along with switch name.
  returned: always
  type: str
changed:
  description: Indicates whether the CLI caused changes on the target.
  returned: always
  type: bool
unreachable:
  description: Indicates whether switch was unreachable to connect.
  returned: always
  type: bool
failed:
  description: Indicates whether or not the execution failed on the target.
  returned: always
  type: bool
exception:
  description: Describes error/exception occurred while executing CLI command.
  returned: always
  type: str
task:
  description: Name of the task getting executed on switch.
  returned: always
  type: str
msg:
  description: Indicates whether configuration made was successful or failed.
  returned: always
  type: str
"""


class BetterIPv4Network(ipaddress.IPv4Network):

    def __add__(self, offset):
        """Add numeric offset to the IP."""
        new_base_addr = int(self.network_address) + offset
        return self.__class__((new_base_addr, str(self.netmask)))

    def size(self):
        """Return network size."""
        start = int(self.network_address)
        return int(self.broadcast_address) + 1 - start


def finding_initial_ip(module, start_ip, subnet_ipv4, count):
    """
    Method to find the intial ip of the ipv4 addressing scheme.
    :param module: The Ansible module to fetch input parameters.
    :param state_ip: start ip of ip addressing scheme.
    :param subnet_ipv4: Subnet to calculate ip address list.
    :return: ip addresses list.
    """
    if  count == 0:
        ips = list(ipaddress.ip_network(start_ip +'/'+subnet_ipv4).hosts())
        return ips
    else:
        network = BetterIPv4Network(start_ip + '/' + subnet_ipv4)
        network_addrs = (network + (i + 1) * network.size() for i in it.count())
        for c in range(count):
            my_range = network_addrs.next()
            ips = list(ipaddress.ip_network(my_range).hosts())

        return ips


def auto_configure_link_ips(module, CHANGED_FLAG, task, msg):
    """
    Method to auto configure link IPs for layer3 fabric.
    :param module: The Ansible module to fetch input parameters.
    :return: String describing output of configuration.
    """
    spine_list = module.params['pn_spine_list']
    leaf_list = module.params['pn_leaf_list']
    addr_type = module.params['pn_addr_type']
    start_ip = unicode(module.params['pn_ipv4_start_address'], "utf-8")
    if addr_type == 'ipv4' or addr_type == 'ipv4_ipv6':
        subnet_ipv4 = unicode(module.params['pn_subnet_ipv4'], "utf-8")
    if addr_type == 'ipv6' or addr_type == 'ipv4_ipv6':
        subnet_ipv6 = module.params['pn_subnet_ipv6']
    current_switch = module.params['pn_current_switch']
    output = ''

    cli = pn_cli(module)
    clicopy = cli

    if current_switch in leaf_list:
        # Disable auto trunk on all switches.
        modify_auto_trunk_setting(module, current_switch, 'disable', task, msg)
        for spine in spine_list:
            # Disable auto trunk.
            modify_auto_trunk_setting(module, spine, 'disable', task, msg)

        # Get the list of available link ips to assign.
        if addr_type == 'ipv6' or addr_type == 'ipv4_ipv6':
            get_count = 2 if subnet_ipv6 == '127' else 3
            available_ips_ipv6 = calculate_link_ip_addresses_ipv6(module.params['pn_net_address_ipv6'],
                                                                  module.params['pn_cidr_ipv6'],
                                                                  subnet_ipv6, get_count)
            for i in range(count_output):
                available_ips_ipv6.next()

        count = leaf_list.index(current_switch) * len(spine_list)
        for spine in spine_list:
            ips = finding_initial_ip(module, start_ip, subnet_ipv4, count)
            cli = clicopy
            cli += ' switch %s port-show hostname %s ' % (current_switch, spine)
            cli += ' format port no-show-headers '
            leaf_port = run_command(module, cli, task, msg).split()
            leaf_port = list(set(leaf_port))

            if 'Success' in leaf_port:
                continue

            while len(leaf_port) > 0:
                ip_ipv6 = ''
                ip_ipv4 = ''
                if addr_type == 'ipv6' or addr_type == 'ipv4_ipv6':
                    try:
                        ip_list = available_ips_ipv6.next()
                    except:
                        msg = 'Error: ipv6 range exhausted'
                        results = {
                            'switch': '',
                            'output': msg
                        }
                        module.exit_json(
                            unreachable=False,
                            failed=True,
                            exception=msg,
                            summary=results,
                            task='L3 ZTP',
                            msg='L3 ZTP failed',
                            changed=False
                        )
                    ip_ipv6 = (ip_list[0] if subnet_ipv6 == '127' else ip_list[1])

                lport = leaf_port[0]

                cli = clicopy
                cli += ' switch %s port-show port %s ' % (current_switch, lport)
                cli += ' format rport no-show-headers '
                rport = run_command(module, cli, task, msg).split()
                rport = list(set(rport))
                rport = rport[0]

                if addr_type == 'ipv4' or addr_type == 'ipv4_ipv6':
                    ip_ipv4 = str(ips[0])

                delete_trunk(module, spine, rport, current_switch, task, msg)
                CHANGED_FLAG, res = create_interface(module, spine, ip_ipv4, ip_ipv6, rport, addr_type, CHANGED_FLAG, task, msg)
                output += res

                leaf_port.remove(lport)
                if addr_type == 'ipv6' or addr_type == 'ipv4_ipv6':
                    ip_ipv6 = (ip_list[1] if subnet_ipv6 == '127' else ip_list[2])

                if addr_type == 'ipv4' or addr_type == 'ipv4_ipv6':
                    ip_ipv4 = str(ips[1])

                delete_trunk(module, current_switch, lport, spine, task, msg)
                CHANGED_FLAG, res = create_interface(module, current_switch, ip_ipv4, ip_ipv6, lport, addr_type, CHANGED_FLAG, task, msg)
                output += res
                count += 1

        # Enable auto trunk on all switches.
        modify_auto_trunk_setting(module, current_switch, 'enable', task, msg)
        for spine in spine_list:
            # Enable auto trunk.
            modify_auto_trunk_setting(module, spine, 'enable', task, msg)

    return output


def main():
    """ This section is for arguments parsing """
    module = AnsibleModule(
        argument_spec=dict(
            pn_current_switch=dict(required=False, type='str'),
            pn_addr_type=dict(required=False, type='str',
                              choices=['ipv4', 'ipv6', 'ipv4_ipv6'], default='ipv4'),
            pn_net_address_ipv4=dict(required=False, type='str', aliases=['pn_ipv4_start_address'],
                                     default='172.168.1.1'),
            pn_net_address_ipv6=dict(required=False, type='str', aliases=['pn_ipv6_start_address']),
            pn_cidr_ipv6=dict(required=False, type='str'),
            pn_subnet_ipv4=dict(required=False, type='str', default='31'),
            pn_subnet_ipv6=dict(required=False, type='str'),
            pn_spine_list=dict(required=False, type='list'),
            pn_leaf_list=dict(required=False, type='list'),
            pn_if_nat_realm=dict(required=False, type='str',
                                 choices=['internal', 'external'], default='internal'),
            pn_update_fabric_to_inband=dict(required=False, type='bool',
                                            default=False),
            pn_bfd=dict(required=False, type='bool', default=False),
            pn_bfd_min_rx=dict(required=False, type='str'),
            pn_bfd_multiplier=dict(required=False, type='str'),
            pn_stp=dict(required=False, type='bool', default=False),
            pn_jumbo_frames=dict(required=False, type='bool', default=False),
        )
    )

    global CHANGED_FLAG
    global task
    global msg

    CHANGED_FLAG = []

    task = 'Configure L3 links',
    msg = 'L3 links configuration failed'

    # L3 setup (link ips)
    message = auto_configure_link_ips(module, CHANGED_FLAG, task, msg)

    # Update fabric network to in-band if flag is True
    if module.params['pn_update_fabric_to_inband']:
        message += update_fabric_network_to_inband(module, module.params['pn_current_switch'], task, msg)

    # Enable STP if flag is True
    if module.params['pn_stp']:
        CHANGED_FLAG, res = modify_stp(module, 'enable', module.params['pn_current_switch'], CHANGED_FLAG, task, msg)
        message += res

    message_string = message
    results = []
    switch_list = module.params['pn_spine_list'] + module.params['pn_leaf_list']

    for switch in switch_list:
        replace_string = switch + ': '
        for line in message_string.splitlines():
            if replace_string in line:
                json_msg = {
                    'switch': switch,
                    'output': (line.replace(replace_string, '')).strip()
                }
                results.append(json_msg)

    # Exit the module and return the required JSON.
    module.exit_json(
        unreachable=False,
        msg='L3 ZTP configuration succeeded',
        summary=results,
        exception='',
        failed=False,
        changed=True if True in CHANGED_FLAG else False,
        task='Configure L3 ZTP'
    )


if __name__ == '__main__':
    main()
