{% set base_domain = 'raxio-hackday.com' %}
{% set email = 'bruce.stringer@rackspace.com' %}
{% set instance_name = 'raxio_instance' %}
{% set db_name = 'raxio_db' %}
{% set container_name = 'raxio_container' %}

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
    - ttl: 700
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
    - name: localhost.{{ base_domain }}
    - record_type: A
    - data: 127.0.0.1
    - require:
      - rackspace: setup_domain

setup_records2:
  rackspace.dns_record_exists:
    - zone_name: {{ base_domain }}
    - name: node1.{{ base_domain }}
    - record_type: A
    - data: {{ grains['ip_interfaces']['eth0']|first }}
    - require:
      - rackspace: setup_domain

setup_database:
  rackspace.db_database_exists:
    - name: {{ db_name }}
    - instance_name: {{ instance_name }}
    - require:
      - rackspace: setup_instance

setup_container:
  rackspace.cf_container_exists:
    - name: {{ container_name }}
    - cnd_enabled: False
    - ttl: 800
    - require:
      - pip: pyrax_setup
