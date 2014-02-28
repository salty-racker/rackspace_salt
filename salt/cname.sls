{% set base_domain = 'raxio-hackday.com' %}
{% set email = 'bruce.stringer@rackspace.com' %}
{% set instance_name = 'raxio_instance' %}
{% set db_name = 'raxio_db' %}
{% set container_name = 'raxio_container' %}

add_cdn_cname:
  rackspace.dns_record_exists:
    - name: cdn.{{ base_domain }}
    - zone_name: {{ base_domain }}
    - record_type: CNAME
    - data: {{ salt['rackspace.cf_container_get'](container_name)['cdn_uri'].rsplit('//')[1] }}
    - requires:
      - rackspace: setup_container



add_instance_cname:
  rackspace.dns_record_exists:
    - name: {{ instance_name }}.{{ base_domain }}
    - zone_name: {{ base_domain }}
    - record_type: CNAME
    - data: {{ salt['rackspace.db_instance_get_by_name'](instance_name)['hostname']}}
    - requires:
      - rackspace: setup_instance