.. _readme:


Curator
=======

Have indices in Elasticsearch? This is the tool for you!

Like a museum curator manages the exhibits and collections on display,
Elasticsearch Curator helps you curate, or manage your indices.

ANNOUNCEMENT
------------

Curator is breaking into version dependent releases. Curator 6.x will work with
Elasticsearch 6.x, Curator 7.x will work with Elasticsearch 7.x, and when it is
released, Curator 8.x will work with Elasticsearch 8.x.

Watch this space for updates when that is coming.

New Client Configuration
------------------------

Curator now connects using the ``es_client`` Python module. This separation makes it much easier
to update the client connection portion separate from Curator. It is largely derived from the
original Curator client configuration, but with important updates.

The updated configuration file structure requires ``elasticsearch`` at the root level::

    ---
    elasticsearch:
      client:
        hosts: https://10.11.12.13:9200
        cloud_id:
        bearer_auth:
        opaque_id:
        request_timeout: 60
        http_compress:
        verify_certs:
        ca_certs:
        client_cert:
        client_key:
        ssl_assert_hostname:
        ssl_assert_fingerprint:
        ssl_version:
      other_settings:
        master_only:
        skip_version_test:
        username:
        password:
        api_key:
          id:
          api_key:

    logging:
      loglevel: INFO
      logfile: /path/to/file.log
      logformat: default
      denylist: []

Action File Configuration
-------------------------

Action file structure is unchanged, for now. A few actions may have had the options modified a bit.
