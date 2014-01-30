{% set base_domain = 'rackspace-saltconf.com' %}
{% set email = 'bruce.stringer@rackspace.com' %}
{% set instance_name = 'salt_conf_instance' %}
{% set db_name = 'salt_conf_db' %}

pyrax_setup:
  pkg.installed:
      - name: python-pip
  pip.installed:
    - name: pyrax
    - require:
      - pkg: pyrax_setup

setup_domain:
  rackspace.dns_zone_exists:
    - name: {{ base_domain }}
    - email_address: {{ email }}
    - ttl: 600
    - require:
      - pip: pyrax_setup

setup_instance:
  rackspace.db_instance_exists:
    - name: {{ instance_name }}
    - size: 1
    - flavor: 1GB Instance
    - require:
      - pip: pyrax_setup


setup_records:
  rackspace.dns_record_exists:
    - zone_name: {{ base_domain }}
    - name: testing.{{ base_domain }}
    - record_type: A
    - data: 127.0.0.1
    - require:
      - rackspace: setup_domain

setup_records2:
  rackspace.dns_record_exists:
    - zone_name: {{ base_domain }}
    - name: testing.{{ base_domain }}
    - record_type: A
    - data: {{ grains['ip_interfaces']['eth0']|first }}
    - allow_multiple_records: True
    - require:
      - rackspace: setup_domain

setup_database:
  rackspace.db_database_exists:
    - name: {{ db_name }}
    - instance_name: {{ instance_name }}
    - require:
      - rackspace: setup_instance


{% if salt['rackspace.db_instance_exists'](instance_name)%}
add_instance_cname:
  rackspace.dns_record_exists:
    - name: {{ instance_name }}.{{ base_domain }}
    - zone_name: {{ base_domain }}
    - record_type: CNAME
    - data: {{ salt['rackspace.db_instance_get_by_name'](instance_name)['hostname']}}
    - requires:
      - rackspace: setup_instance
{% endif %}