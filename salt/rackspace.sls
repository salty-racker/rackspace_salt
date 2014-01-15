python-pip:
  pkg.installed

pyrax:
  pip.installed:
    - require:
      - pkg: python-pip

setup_db:
  rackspace.db_instance_exists:
    - name: test123
    - size: 1
    - flavor: 1GB Instance
    - require:
      - pip: pyrax

setup_db_2:
  rackspace.db_instance_exists:
    - name: testing_new_db
    - size: 1
    - flavor: 1GB Instance
    - require:
      - pip: pyrax

setup_domain:
  rackspace.dns_zone_exists:
    - name: testingrackspacesalt1.com
    - emailAddress: bruce.stringer@rackspace.com
    - ttl: 600
    - require:
      - pip: pyrax

setup_records:
  rackspace.dns_record_exists:
    - zone_name: testingrackspacesalt1.com
    - name: testing.testingrackspacesalt1.com
    - record_type: A
    - data: 127.0.0.1
    - allow_multiple_records: True
    - require:
      - rackspace: setup_domain

setup_records2:
  rackspace.dns_record_exists:
    - zone_name: testingrackspacesalt1.com
    - name: testing.testingrackspacesalt1.com
    - record_type: A
    - data: 127.0.0.2
    - allow_multiple_records: True
    - require:
      - rackspace: setup_domain

setup_records3:
  rackspace.dns_record_exists:
    - zone_name: testingrackspacesalt1.com
    - name: testing.testingrackspacesalt1.com
    - record_type: A
    - data: 127.0.0.3
    - allow_multiple_records: True
    - require:
      - rackspace: setup_domain
