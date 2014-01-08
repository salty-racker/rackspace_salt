setup_db:
  rackspace.db_instance_exists:
    - name: test123
    - size: 1
    - flavor: 1GB Instance


setup_domain:
  rackspace.dns_zone_exists:
    - name: testingrackspacesalt1.com
    - emailAddress: bruce.stringer@rackspace.com
    - ttl: 600

setup_records:
  rackspace.dns_record_exists:
    - zone_name: testingrackspacesalt1.com
    - name: testing.testingrackspacesalt1.com
    - record_type: A
    - data: 127.0.0.1
    - require:
      - rackspace: setup_domain


