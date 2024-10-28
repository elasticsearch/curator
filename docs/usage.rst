.. _usage:

Using Curator
#############

Compatibility
=============

Elasticsearch Curator version 8 is compatible with Elasticsearch version 8.x, and supports Python
versions 3.8, 3.9, 3.10, and 3.11 officially.

Installation
============

Install the ``elasticsearch-curator`` package with `pip
<https://pypi.python.org/pypi/elasticsearch-curator>`_::

    pip install elasticsearch-curator

Command-Line Usage
==================

The documentation for this is on
`Elastic's Website <https://www.elastic.co/guide/en/elasticsearch/client/curator/current/index.html>`_.

Example API Usage
=================

.. code-block:: python

    import elasticsearch8
    import curator

    client = elasticsearch8.Elasticsearch()

    ilo = curator.IndexList(client)
    ilo.filter_by_regex(kind='prefix', value='logstash-')
    ilo.filter_by_age(source='name', direction='older', timestring='%Y.%m.%d', unit='days', unit_count=30)
    delete_indices = curator.DeleteIndices(ilo)
    delete_indices.do_action()

.. TIP::
    See more examples in the :doc:`Examples </examples>` page.

Logging
=======

Elasticsearch Curator uses the standard `logging library`_ from Python. It inherits the
``ecs-logging`` formatting module from ``es_client``, which inherits the ``elastic_transport``
logger from ``elasticsearch8``. Clients use the ``elastic_transport`` logger to log standard
activity, depending on the log level.

It is recommended to use :py:class:`~.es_client.helpers.logging.set_logging` to enable
logging, as this has been provided for you.

This is quite simple:

.. code-block:: python

    from es_client.helpers.logging import set_logging
    import logging

    LOG = {
      'loglevel': 'INFO',
      'logfile': None,
      'logformat': 'default',
      'denylist': ['elastic_transport', 'urllib3']
    }

    set_logging(LOG)
    logger = logging.getLogger(__name__)
    logger.info('Sample log message')

That's it! If you were to save this file and run it at the command-line, you would see:

.. code-block:: shell

    $ python logtest.py
    2023-02-10 20:26:52,262 INFO      Sample log message

Log Settings
------------

Available settings for ``loglevel`` are: ``NOTSET``, ``DEBUG``, ``INFO``, ``WARNING``, ``ERROR``,
and ``CRITICAL``.

The setting ``logfile`` must be ``None`` or a path to a writeable file. If ``None``, it will log to
``STDOUT``.

Available settings for ``logformat`` are: ``default``, ``json``, and ``ecs``. The ``ecs`` option
uses `the Python ECS Log Formatter`_ and is great if you plan on ingesting your logs into
Elasticsearch.

Denylisting logs by way of the ``denylist`` setting should remain configured with the defaults
(``['elastic_transport', 'urllib3']``), unless you are troubleshooting a connection issue. The
``elastic_transport`` and ``urllib3`` modules logging is exceptionally chatty for inclusion with
Curator action tracing.

.. _the Python ECS Log Formatter: https://www.elastic.co/guide/en/ecs-logging/python/current/index.html
.. _logging library: http://docs.python.org/3.11/library/logging.html