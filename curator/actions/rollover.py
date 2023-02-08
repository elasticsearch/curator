"""Open index action class"""
import logging
from curator.exceptions import ConfigurationError
from curator.helpers.date_ops import parse_date_pattern
from curator.helpers.testers import rollable_alias, verify_client_object
from curator.helpers.utils import report_failure

class Rollover:
    """Rollover Action Class"""
    def __init__(
            self, client, name=None, conditions=None, new_index=None, extra_settings=None,
            wait_for_active_shards=1
        ):
        """
        :arg client: An :class:`elasticsearch.Elasticsearch` client object
        :arg name: The name of the single-index-mapped alias to test for
            rollover conditions.
        :new_index: The new index name
        :arg conditions: A dictionary of conditions to test
        :arg extra_settings: Must be either `None`, or a dictionary of settings
            to apply to the new index on rollover. This is used in place of
            `settings` in the Rollover API, mostly because it's already existent
            in other places here in Curator
        :arg wait_for_active_shards: The number of shards expected to be active
            before returning.
        """
        self.loggit = logging.getLogger('curator.actions.rollover')
        if not isinstance(conditions, dict):
            raise ConfigurationError('"conditions" must be a dictionary')
        else:
            self.loggit.debug('"conditions" is %s', conditions)
        if not isinstance(extra_settings, dict) and extra_settings is not None:
            raise ConfigurationError(
                '"extra_settings" must be a dictionary or None')
        verify_client_object(client)
        #: Instance variable.
        #: The Elasticsearch Client object
        self.client = client
        #: Instance variable.
        #: Internal reference to `conditions`
        self.conditions = conditions
        #: Instance variable.
        #: Internal reference to `extra_settings`
        self.settings = extra_settings
        #: Instance variable.
        #: Internal reference to `new_index`
        self.new_index = parse_date_pattern(new_index) if new_index else new_index
        #: Instance variable.
        #: Internal reference to `wait_for_active_shards`
        self.wait_for_active_shards = wait_for_active_shards

        # Verify that `conditions` and `settings` are good?
        # Verify that `name` is an alias, and is only mapped to one index.
        if rollable_alias(client, name):
            self.name = name
        else:
            raise ValueError(
                f'Unable to perform index rollover with alias '
                f'"{name}". See previous logs for more details.'
            )

    def log_result(self, result):
        """
        Log the results based on whether the index rolled over or not
        """
        dryrun_string = ''
        if result['dry_run']:
            dryrun_string = 'DRY-RUN: '
        self.loggit.debug('%sResult: %s', dryrun_string, result)
        rollover_string = (
            f"{dryrun_string}Old index {result['old_index']} "
            f"rolled over to new index {result['new_index']}"
        )
        # Success is determined by at one condition being True
        success = False
        for k in list(result['conditions'].keys()):
            if result['conditions'][k]:
                success = True
        if result['dry_run'] and success: # log "successful" dry-run
            self.loggit.info(rollover_string)
        elif result['rolled_over']:
            self.loggit.info(rollover_string)
        else:
            msg = (
                f"{dryrun_string}Rollover conditions not met. "
                f"Index {result['old_index']} not rolled over."
            )
            self.loggit.info(msg)

    def doit(self, dry_run=False):
        """
        This exists solely to prevent having to have duplicate code in both
        `do_dry_run` and `do_action`
        """
        return self.client.indices.rollover(
            alias=self.name,
            new_index=self.new_index,
            conditions=self.conditions,
            settings=self.settings,
            dry_run=dry_run,
            wait_for_active_shards=self.wait_for_active_shards,
        )

    def do_dry_run(self):
        """
        Log what the output would be, but take no action.
        """
        self.loggit.info('DRY-RUN MODE.  No changes will be made.')
        self.log_result(self.doit(dry_run=True))

    def do_action(self):
        """
        Rollover the index referenced by alias `name`
        """
        self.loggit.info('Performing index rollover')
        try:
            self.log_result(self.doit())
        # pylint: disable=broad-except
        except Exception as err:
            report_failure(err)
