setup_db:
  rackspace.db_instance_exists:
    - name: test123
    - size: 1
    - flavor: 1GB Instance


setup_domain:
  rackspace.dns_domain_exists:
    - name: testingrackspacesalt.com
    - emailAddress: bruce.stringer@rackspace.com
    - ttl: 600