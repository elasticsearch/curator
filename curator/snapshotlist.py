"""SnapshotList"""
import re
import logging
from es_client.helpers.schemacheck import SchemaCheck
from curator.exceptions import ConfigurationError, FailedExecution, MissingArgument, NoSnapshots
from curator.helpers.date_ops import (
    absolute_date_range, date_range, fix_epoch, get_date_regex, get_point_of_reference,
    TimestringSearch
)
from curator.helpers.getters import get_snapshot_data
from curator.helpers.testers import repository_exists, verify_client_object
from curator.helpers.utils import report_failure
from curator.defaults import settings
from curator.validators.filter_functions import filterstructure

class SnapshotList:
    """Snapshot list object"""
    def __init__(self, client, repository=None):
        verify_client_object(client)
        if not repository:
            raise MissingArgument('No value for "repository" provided')
        if not repository_exists(client, repository):
            raise FailedExecution(
                f'Unable to verify existence of repository {repository}')
        self.loggit = logging.getLogger('curator.snapshotlist')
        #: An :py:class:`~.elasticsearch.Elasticsearch` client object passed from param ``client``
        self.client = client
        #: The value passed as ``delete_aliases``
        self.repository = repository
        #: Information extracted from snapshots, such as age, etc.
        #: Populated by internal method ``__get_snapshots`` at instance creation
        #: time. **Type:** :py:class:`dict`
        self.snapshot_info = {}
        #: The running list of snapshots which will be used by an Action class.
        #: Populated by internal methods ``__get_snapshots`` at instance creation
        #: time. **Type:** :py:class:`list`
        self.snapshots = []
        #: Raw data dump of all snapshots in the repository at instance creation
        #: time.  **Type:** :py:class:`list` of :py:class:`dict` data.
        self.__get_snapshots()
        self.age_keyfield = None

    def __actionable(self, snap):
        self.loggit.debug(
            'Snapshot %s is actionable and remains in the list.', snap)

    def __not_actionable(self, snap):
        self.loggit.debug('Snapshot %s is not actionable, removing from list.', snap)
        self.snapshots.remove(snap)

    def __excludify(self, condition, exclude, snap, msg=None):
        if condition:
            if exclude:
                text = "Removed from actionable list"
                self.__not_actionable(snap)
            else:
                text = "Remains in actionable list"
                self.__actionable(snap)
        else:
            if exclude:
                text = "Remains in actionable list"
                self.__actionable(snap)
            else:
                text = "Removed from actionable list"
                self.__not_actionable(snap)
        if msg:
            self.loggit.debug('%s: %s', text, msg)

    def __get_snapshots(self):
        """
        Pull all snapshots into `snapshots` and populate ``snapshot_info``
        """
        self.all_snapshots = get_snapshot_data(self.client, self.repository)
        for list_item in self.all_snapshots:
            if 'snapshot' in list_item.keys():
                self.snapshots.append(list_item['snapshot'])
                self.snapshot_info[list_item['snapshot']] = list_item
        self.empty_list_check()

    def __map_method(self, ftype):
        methods = {
            'age': self.filter_by_age,
            'count': self.filter_by_count,
            'none': self.filter_none,
            'pattern': self.filter_by_regex,
            'period': self.filter_period,
            'state': self.filter_by_state,
        }
        return methods[ftype]

    def empty_list_check(self):
        """Raise exception if ``snapshots`` is empty"""
        if not self.snapshots:
            raise NoSnapshots('snapshot_list object is empty.')

    def working_list(self):
        """
        Return the current value of ``snapshots`` as copy-by-value to prevent list stomping during
        iterations
        """
        # Copy by value, rather than reference to prevent list stomping during
        # iterations
        return self.snapshots[:]

    def _get_name_based_ages(self, timestring):
        """
        Add a snapshot age to ``snapshot_info`` based on the age as indicated by the snapshot name
        pattern, if it matches ``timestring``.  This is stored at key ``age_by_name``.

        :param timestring: A :py:func:`time.strftime` pattern
        """
        # Check for empty list before proceeding here to prevent non-iterable
        # condition
        self.empty_list_check()
        tstamp = TimestringSearch(timestring)
        for snapshot in self.working_list():
            epoch = tstamp.get_epoch(snapshot)
            if epoch:
                self.snapshot_info[snapshot]['age_by_name'] = epoch
            else:
                self.snapshot_info[snapshot]['age_by_name'] = None

    def _calculate_ages(self, source='creation_date', timestring=None):
        """
        This method initiates snapshot age calculation based on the given parameters.  Exceptions
        are raised when they are improperly configured.

        Set instance variable ``age_keyfield`` for use later, if needed.

        :param source: Source of snapshot age. Can be ``name`` or ``creation_date``.
        :param timestring: An :py:func:`time.strftime` string to match the datestamp in an snapshot name. Only used
            if ``source=name``.
        """
        if source == 'name':
            self.age_keyfield = 'age_by_name'
            if not timestring:
                raise MissingArgument('source "name" requires the "timestring" keyword argument')
            self._get_name_based_ages(timestring)
        elif source == 'creation_date':
            self.age_keyfield = 'start_time_in_millis'
        else:
            raise ValueError(f'Invalid source: {source}. Must be "name", or "creation_date".')

    def _sort_by_age(self, snapshot_list, reverse=True):
        """
        Take a list of snapshots and sort them by date.

        By default, the youngest are first with ``reverse=True``, but the oldest can be first by
        setting ``reverse=False``
        """
        # Do the age-based sorting here.
        # First, build an temporary dictionary with just snapshot and age
        # as the key and value, respectively
        temp = {}
        for snap in snapshot_list:
            if self.age_keyfield in self.snapshot_info[snap]:
                # This fixes #1366. Catch None is a potential age value.
                if self.snapshot_info[snap][self.age_keyfield]:
                    temp[snap] = self.snapshot_info[snap][self.age_keyfield]
                else:
                    msg = ' snapshot %s has no age' % snap
                    self.__excludify(True, True, snap, msg)
            else:
                msg = (
                    f'{snap} does not have age key "{self.age_keyfield}" in SnapshotList metadata')
                self.__excludify(True, True, snap, msg)

        # If reverse is True, this will sort so the youngest snapshots are
        # first.  However, if you want oldest first, set reverse to False.
        # Effectively, this should set us up to act on everything older than
        # meets the other set criteria.
        # It starts as a tuple, but then becomes a list.
        sorted_tuple = (
            sorted(temp.items(), key=lambda k: k[1], reverse=reverse)
        )
        return [x[0] for x in sorted_tuple]

    def most_recent(self):
        """
        Return the most recent snapshot based on ``start_time_in_millis``.
        """
        self.empty_list_check()
        most_recent_time = 0
        most_recent_snap = ''
        for snapshot in self.snapshots:
            snaptime = fix_epoch(self.snapshot_info[snapshot]['start_time_in_millis'])
            if snaptime > most_recent_time:
                most_recent_snap = snapshot
                most_recent_time = snaptime
        return most_recent_snap


    def filter_by_regex(self, kind=None, value=None, exclude=False):
        """
        Filter out snapshots not matching the pattern, or in the case of
        exclude, filter those matching the pattern.

        :param kind: Can be one of: ``suffix``, ``prefix``, ``regex``, or
            ``timestring``. This option defines what kind of filter you will be
            building.
        :param value: Depends on ``kind``. It is the :py:func:`time.strftime` string if ``kind`` is
            ``timestring``. It's used to build the regular expression for other kinds.
        :param exclude: If ``exclude=True``, this filter will remove matching snapshots from
            ``snapshots``. If ``exclude=False``, then only matching snapshots will be kept in
            ``snapshots``. Default is ``False``
        """
        if kind not in ['regex', 'prefix', 'suffix', 'timestring']:
            raise ValueError(f'{kind}: Invalid value for kind')

        # Stop here if None or empty value, but zero is okay
        if value == 0:
            pass
        elif not value:
            raise ValueError(
                f'{value}: Invalid value for "value". Cannot be "None" type, empty, or False')

        if kind == 'timestring':
            regex = settings.regex_map()[kind].format(get_date_regex(value))
        else:
            regex = settings.regex_map()[kind].format(value)

        self.empty_list_check()
        pattern = re.compile(regex)
        for snapshot in self.working_list():
            match = pattern.search(snapshot)
            self.loggit.debug('Filter by regex: Snapshot: %s', snapshot)
            if match:
                self.__excludify(True, exclude, snapshot)
            else:
                self.__excludify(False, exclude, snapshot)

    def filter_by_age(
            self, source='creation_date', direction=None, timestring=None, unit=None,
            unit_count=None, epoch=None, exclude=False):
        """
        Remove snapshots from ``snapshots`` by relative age calculations.

        :param source: Source of snapshot age. Can be ``name``, or ``creation_date``.
        :param direction: Time to filter, either ``older`` or ``younger``
        :param timestring: A :py:func:`time.strftime` string to match the datestamp in an snapshot
            name. Only used for snapshot filtering by ``name``.
        :param unit: One of ``seconds``, ``minutes``, ``hours``, ``days``, ``weeks``, ``months``, or
            ``years``.
        :param unit_count: The number of ``unit`` (s). ``unit_count`` * ``unit`` will be calculated
            out to the relative number of seconds.
        :param epoch: An epoch timestamp used in conjunction with ``unit`` and ``unit_count`` to
            establish a point of reference for calculations. If not provided, the current time will
            be used.
        :param exclude: If ``exclude=True``, this filter will remove matching snapshots from
            ``snapshots``. If ``exclude=False``, then only matching snapshots will be kept in
            ``snapshots``. Default is ``False``
        """
        self.loggit.debug('Starting filter_by_age')
        # Get timestamp point of reference, por
        por = get_point_of_reference(unit, unit_count, epoch)
        self.loggit.debug('Point of Reference: %s', por)
        if not direction:
            raise MissingArgument('Must provide a value for "direction"')
        if direction not in ['older', 'younger']:
            raise ValueError(f'Invalid value for "direction": {direction}')
        self._calculate_ages(source=source, timestring=timestring)
        for snapshot in self.working_list():
            if not self.snapshot_info[snapshot][self.age_keyfield]:
                self.loggit.debug('Removing snapshot %s for having no age', snapshot)
                self.snapshots.remove(snapshot)
                continue
            age = fix_epoch(self.snapshot_info[snapshot][self.age_keyfield])
            msg = (
                f'Snapshot "{snapshot}" age ({age}), direction: "{direction}", point of '
                f'reference, ({por})'
            )
            # Because time adds to epoch, smaller numbers are actually older
            # timestamps.
            snapshot_age = fix_epoch(self.snapshot_info[snapshot][self.age_keyfield])
            if direction == 'older':
                agetest = snapshot_age < por
            else: # 'younger'
                agetest = snapshot_age > por
            self.__excludify(agetest, exclude, snapshot, msg)

    def filter_by_state(self, state=None, exclude=False):
        """
        Filter out snapshots not matching ``state``, or in the case of exclude, filter those
        matching ``state``.

        :param state: The snapshot state to filter for. Must be one of ``SUCCESS``, ``PARTIAL``,
            ``FAILED``, or ``IN_PROGRESS``.
        :param exclude: If ``exclude=True``, this filter will remove matching snapshots from
            ``snapshots``. If ``exclude=False``, then only matching snapshots will be kept in
            ``snapshots``. Default is ``False``
        """
        if state.upper() not in ['SUCCESS', 'PARTIAL', 'FAILED', 'IN_PROGRESS']:
            raise ValueError(f'{state}: Invalid value for state')
        self.empty_list_check()
        for snapshot in self.working_list():
            self.loggit.debug('Filter by state: Snapshot: %s', snapshot)
            if self.snapshot_info[snapshot]['state'] == state:
                self.__excludify(True, exclude, snapshot)
            else:
                self.__excludify(False, exclude, snapshot)

    def filter_none(self):
        """No filter at all"""
        self.loggit.debug('"None" filter selected.  No filtering will be done.')

    def filter_by_count(
            self, count=None, reverse=True, use_age=False,
            source='creation_date', timestring=None, exclude=True
    ):
        """
        Remove snapshots from the actionable list beyond the number ``count``, sorted
        reverse-alphabetically by default.  If you set ``reverse=False``, it will be sorted
        alphabetically.

        The default is usually what you will want. If only one kind of snapshot is provided--for
        example, snapshots matching ``curator-%Y%m%d%H%M%S``--then reverse alphabetical sorting
        will mean the oldest will remain in the list, because lower numbers in the dates mean older
        snapshots.

        By setting ``reverse=False``, then ``snapshot3`` will be acted on before ``snapshot2``,
        which will be acted on before ``snapshot1``

        ``use_age`` allows ordering snapshots by age. Age is determined by the snapshot creation
        date (as identified by ``start_time_in_millis``) by default, but you can also specify
        ``source=name``.  The ``name`` ``source`` requires the timestring argument.

        :param count: Filter snapshots beyond ``count``.
        :param reverse: The filtering direction. (default: ``True``).
        :param use_age: Sort snapshots by age.  ``source`` is required in this case.
        :param source: Source of snapshot age. Can be one of ``name``, or ``creation_date``.
            Default: ``creation_date``
        :param timestring: A :py:func:`time.strftime` string to match the datestamp in a snapshot
            name. Only used if ``source=name``.
        :param exclude: If ``exclude=True``, this filter will remove matching snapshots from
            ``snapshots``. If ``exclude=False``, then only matching snapshots will be kept in
            ``snapshots``. Default is ``True``
        """
        self.loggit.debug('Filtering snapshots by count')
        if not count:
            raise MissingArgument('No value for "count" provided')
        # Create a copy-by-value working list
        working_list = self.working_list()
        if use_age:
            self._calculate_ages(source=source, timestring=timestring)
            # Using default value of reverse=True in self._sort_by_age()
            sorted_snapshots = self._sort_by_age(working_list, reverse=reverse)
        else:
            # Default to sorting by snapshot name
            sorted_snapshots = sorted(working_list, reverse=reverse)
        idx = 1
        for snap in sorted_snapshots:
            msg = (f'{snap} is {idx} of specified count of {count}.')
            condition = True if idx <= count else False
            self.__excludify(condition, exclude, snap, msg)
            idx += 1

    def filter_period(self, period_type='relative', source='name', range_from=None,
        range_to=None, date_from=None, date_to=None, date_from_format=None, date_to_format=None,
        timestring=None, unit=None, week_starts_on='sunday', epoch=None, exclude=False):
        """
        Match ``snapshots`` with ages within a given period.

        :param period_type: Can be either ``absolute`` or ``relative``.  Default is ``relative``.
            ``date_from`` and ``date_to`` are required when using ``period_type='absolute'``.
            ``range_from`` and ``range_to`` are required with ``period_type='relative'``.
        :param source: Source of snapshot age. Can be ``name``, or ``creation_date``.
        :param range_from: How many ``unit`` (s) in the past/future is the origin?
        :param range_to: How many ``unit`` (s) in the past/future is the end point?
        :param date_from: The simplified date for the start of the range
        :param date_to: The simplified date for the end of the range.  If this value
            is the same as ``date_from``, the full value of ``unit`` will be
            extrapolated for the range.  For example, if ``unit=months``,
            and ``date_from`` and ``date_to`` are both ``2017.01``, then the entire
            month of January 2017 will be the absolute date range.
        :param date_from_format: The :py:func:`time.strftime` string used to parse ``date_from``
        :param date_to_format: The :py:func:`time.strftime` string used to parse ``date_to``
        :param timestring: An :py:func:`time.strftime` string to match the datestamp in an
            snapshot name. Only used for snapshot filtering by ``name``.
        :param unit: One of ``hours``, ``days``, ``weeks``, ``months``, or ``years``.
        :param week_starts_on: Either ``sunday`` or ``monday``. Default is ``sunday``
        :param epoch: An epoch timestamp used to establish a point of reference
            for calculations. If not provided, the current time will be used.
        :param exclude: If ``exclude=True``, this filter will remove matching indices from
            ``indices``. If ``exclude=False``, then only matching indices will be kept in
            ``indices``. Default is ``False``
        """
        self.loggit.debug('Filtering snapshots by period')
        if period_type not in ['absolute', 'relative']:
            raise ValueError(
                f'Unacceptable value: {period_type} -- "period_type" must be either '
                f'"absolute" or "relative".'
            )
        self.loggit.debug('period_type = %s', period_type)
        if period_type == 'relative':
            func = date_range
            args = [unit, range_from, range_to, epoch]
            kwgs = {'week_starts_on': week_starts_on}
            try:
                range_from = int(range_from)
                range_to = int(range_to)
            except ValueError as err:
                raise ConfigurationError(
                    f'"range_from" and "range_to" must be integer values. Error: {err}') from err
        else:
            func = absolute_date_range
            args = [unit, date_from, date_to]
            kwgs = {
                'date_from_format': date_from_format,
                'date_to_format': date_to_format
            }
            for reqd in [date_from, date_to, date_from_format, date_to_format]:
                if not reqd:
                    raise ConfigurationError(
                        'Must provide "date_from", "date_to", '
                        '"date_from_format", and "date_to_format" with absolute period_type'
                    )
        try:
            start, end = func(*args, **kwgs)
        # pylint: disable=broad-except
        except Exception as err:
            report_failure(err)
        self._calculate_ages(source=source, timestring=timestring)
        for snapshot in self.working_list():
            if not self.snapshot_info[snapshot][self.age_keyfield]:
                self.loggit.debug('Removing snapshot {0} for having no age')
                self.snapshots.remove(snapshot)
                continue
            age = fix_epoch(self.snapshot_info[snapshot][self.age_keyfield])
            msg = (
                f'Snapshot "{snapshot}" age ({age}), period start: "{start}", period '
                f'end, ({end})'
            )
            # Because time adds to epoch, smaller numbers are actually older
            # timestamps.
            inrange = ((age >= start) and (age <= end))
            self.__excludify(inrange, exclude, snapshot, msg)

    def iterate_filters(self, config):
        """
        Iterate over the filters defined in ``config`` and execute them.

        :param config: A dictionary of filters, as extracted from the YAML configuration file.

        .. note:: ``config`` should be a dictionary with the following form:
        .. code-block:: python

                { 'filters' : [
                        {
                            'filtertype': 'the_filter_type',
                            'key1' : 'value1',
                            ...
                            'keyN' : 'valueN'
                        }
                    ]
                }

        """
        # Make sure we actually _have_ filters to act on
        if not 'filters' in config or not config['filters']:
            self.loggit.info('No filters in config.  Returning unaltered object.')
            return
        self.loggit.debug('All filters: %s', config['filters'])
        for fltr in config['filters']:
            f = f.copy()
            self.loggit.debug('Top of the loop: %s', self.snapshots)
            self.loggit.debug('Un-parsed filter args: %s', fltr)
            filter_result = SchemaCheck(
                fltr, filterstructure(), 'filter', 'SnapshotList.iterate_filters').result()
            self.loggit.debug('Parsed filter args: %s', filter_result)
            method = self.__map_method(fltr['filtertype'])
            # Remove key 'filtertype' from dictionary 'fltr'
            del fltr['filtertype']
            # If it's a filtertype with arguments, update the defaults with the
            # provided settings.
            self.loggit.debug('Filter args: %s', fltr)
            self.loggit.debug('Pre-instance: %s', self.snapshots)
            method(**fltr)
            self.loggit.debug('Post-instance: %s', self.snapshots)
