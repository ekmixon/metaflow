import json
import os
import re
import time
from collections import namedtuple
from datetime import datetime

from metaflow.exception import MetaflowInternalError
from metaflow.util import get_username, resolve_identity


DataArtifact = namedtuple('DataArtifact',
                          'name ds_type ds_root url type sha')

MetaDatum = namedtuple('MetaDatum',
                       'field value type tags')

attempt_id_re = re.compile(r"attempt_id:([0-9]+)")

class MetadataProviderMeta(type):
    def __new__(metaname, classname, bases, attrs):
        return type.__new__(metaname, classname, bases, attrs)

    def _get_info(classobject):
        if not classobject._INFO:
            classobject._INFO = classobject.default_info()
        return classobject._INFO

    def _set_info(classobject, val):
        v = classobject.compute_info(val)
        classobject._INFO = v

    def __init__(classobject, classname, bases, attrs):
        classobject._INFO = None

    INFO = property(_get_info, _set_info)


# From https://stackoverflow.com/questions/22409430/portable-meta-class-between-python2-and-python3
def with_metaclass(mcls):
    def decorator(cls):
        body = vars(cls).copy()
        # clean out class body
        body.pop('__dict__', None)
        body.pop('__weakref__', None)
        return mcls(cls.__name__, cls.__bases__, body)
    return decorator


@with_metaclass(MetadataProviderMeta)
class MetadataProvider(object):

    @classmethod
    def compute_info(cls, val):
        '''
        Compute the new information for this provider

        The computed value should be returned and will then be accessible directly as cls.INFO.
        This information will be printed by the client when describing this metadata provider

        Parameters
        ----------
        val : str
            Provider specific information used in computing the new information. For example, this
            can be a path.

        Returns
        -------
        str :
            Value to be set to INFO
        '''
        return ''

    @classmethod
    def default_info(cls):
        '''
        Returns the default information for this provider

        This should compute and return the default value for the information regarding this provider.
        For example, this can compute where the metadata is stored

        Returns
        -------
        str
            Value to be set by default in INFO
        '''
        return ''

    def version(self):
        '''
        Returns the version of this provider

        Returns
        -------
        str
            Version of the provider
        '''
        return ''

    def new_run_id(self, tags=None, sys_tags=None):
        '''
        Creates an ID and registers this new run.

        The run ID will be unique within a given flow.

        Parameters
        ----------
        tags : list, optional
            Tags to apply to this particular run, by default None
        sys_tags : list, optional
            System tags to apply to this particular run, by default None

        Returns
        -------
        int
            Run ID for the run
        '''
        raise NotImplementedError()

    def register_run_id(self, run_id, tags=None, sys_tags=None):
        '''
        No-op operation in this implementation.

        Parameters
        ----------
        run_id : int
            Run ID for this run
        tags : list, optional
            Tags to apply to this particular run, by default None
        sys_tags : list, optional
            System tags to apply to this particular run, by default None
        '''
        raise NotImplementedError()

    def new_task_id(self, run_id, step_name, tags=None, sys_tags=None):
        '''
        Creates an ID and registers this new task.

        The task ID will be unique within a flow, run and step

        Parameters
        ----------
        run_id : int
            ID of the run
        step_name : string
            Name of the step
        tags : list, optional
            Tags to apply to this particular task, by default None
        sys_tags : list, optional
            System tags to apply to this particular task, by default None

        Returns
        -------
        int
            Task ID for the task
        '''
        raise NotImplementedError()

    def register_task_id(
            self, run_id, step_name, task_id, attempt=0, tags=None, sys_tags=None):
        '''
        No-op operation in this implementation.

        Parameters
        ----------
        run_id : int or convertible to int
            Run ID for this run
        step_name : string
            Name of the step
        task_id : int
            Task ID
        tags : list, optional
            Tags to apply to this particular run, by default []
        sys_tags : list, optional
            System tags to apply to this particular run, by default []
        '''
        raise NotImplementedError()

    def get_runtime_environment(self, runtime_name):
        '''
        Returns a dictionary of environment variables to be set

        Parameters
        ----------
        runtime_name : string
            Name of the runtime for which to get the environment

        Returns
        -------
        dict[string] -> string
            Environment variables from this metadata provider
        '''
        return {'METAFLOW_RUNTIME_NAME': runtime_name,
                'USER': get_username()}

    def register_data_artifacts(self,
                                run_id,
                                step_name,
                                task_id,
                                attempt_id,
                                artifacts):
        '''
        Registers the fact that the data-artifacts are associated with
        the particular task.

        Artifacts produced by a given task can be associated with the
        task using this call

        Parameters
        ----------
        run_id : int
            Run ID for the task
        step_name : string
            Step name for the task
        task_id : int
            Task ID for the task
        attempt_id : int
            Attempt for the task
        artifacts : List of DataArtifact
            Artifacts associated with this task
        '''
        raise NotImplementedError()

    def register_metadata(self, run_id, step_name, task_id, metadata):
        '''
        Registers metadata with a task.

        Note that the same metadata can be registered multiple times for the same task (for example
        by multiple attempts). Internally, the timestamp of when the registration call is made is
        also recorded allowing the user to determine the latest value of the metadata.

        Parameters
        ----------
        run_id : int
            Run ID for the task
        step_name : string
            Step name for the task
        task_id : int
            Task ID for the task
        metadata : List of MetaDatum
            Metadata associated with this task
        '''
        raise NotImplementedError()

    def start_task_heartbeat(self, flow_id, run_id, step_name, task_id):
        pass

    def start_run_heartbeat(self, flow_id, run_id):
        pass

    def stop_heartbeat(self):
        pass

    @classmethod
    def _get_object_internal(
        cls, obj_type, obj_order, sub_type, sub_order, filters, attempt, *args):
        '''
        Return objects for the implementation of this class

        See get_object_internal for the description of what this function does

        Parameters
        ----------
        obj_type : string
            One of 'root', 'flow', 'run', 'step', 'task', 'artifact'
        obj_order: int
            Order in the list ['root', 'flow', 'run', 'step', 'task', 'artifact']
        sub_type : string
            Same as obj_type with the addition of 'metadata', 'self'
        sub_order:
            Order in the same list as the one for obj_order + ['metadata', 'self']
        filters : dict
            Dictionary with keys 'any_tags', 'tags' and 'system_tags'. If specified
            will return only objects that have the specified tags present. Filters
            are ANDed together so all tags must be present for the object to be returned.
        attempt : int or None
            If None, returns artifacts for latest *done* attempt and all metadata. Otherwise,
            returns artifacts for that attempt (existent, done or not) and *all* metadata
            NOTE: Unlike its external facing `get_object`, this function should
            return *all* metadata; the base class will properly implement the
            filter. For artifacts, this function should filter artifacts at
            the backend level.

        Return
        ------
            object or list :
                Depending on the call, the type of object return varies
        '''
        raise NotImplementedError()

    def add_sticky_tags(self, tags=None, sys_tags=None):
        '''
        Adds tags to be added to every run and task

        Tags can be added to record information about a run/task. Such tags can be specified on a
        per run or task basis using the new_run_id/register_run_id or new_task_id/register_task_id
        functions but can also be set globally using this function. Tags added here will be
        added to every run/task created after this call is made.

        Parameters
        ----------
        tags : list, optional
            Tags to add to every run/task, by default None
        sys_tags : list, optional
            System tags to add to every run/task, by default None
        '''
        if tags:
            self.sticky_tags.update(tags)
        if sys_tags:
            self.sticky_sys_tags.update(sys_tags)

    @classmethod
    def get_object(cls, obj_type, sub_type, filters, attempt, *args):
        '''Returns the requested object depending on obj_type and sub_type

        obj_type can be one of 'root', 'flow', 'run', 'step', 'task',
        or 'artifact'

        sub_type describes the aggregation required and can be either:
        'metadata', 'self' or any of obj_type provided that it is slotted below
        the object itself. For example, if obj_type is 'flow', you can
        specify 'run' to get all the runs in that flow.
        A few special rules:
            - 'metadata' is only allowed for obj_type 'task'
            - For obj_type 'artifact', only 'self' is allowed
        A few examples:
            - To get a list of all flows:
                - set obj_type to 'root' and sub_type to 'flow'
            - To get a list of all tasks:
                - set obj_type to 'root' and sub_type to 'task'
            - To get a list of all artifacts in a task:
                - set obj_type to 'task' and sub_type to 'artifact'
            - To get information about a specific flow:
                - set obj_type to 'flow' and sub_type to 'self'

        Parameters
        ----------
        obj_type : string
            One of 'root', 'flow', 'run', 'step', 'task', 'artifact' or 'metadata'
        sub_type : string
            Same as obj_type with the addition of 'self'
        filters : dict
            Dictionary with keys 'any_tags', 'tags' and 'system_tags'. If specified
            will return only objects that have the specified tags present. Filters
            are ANDed together so all tags must be present for the object to be returned.
        attempt : int or None
            If None, for metadata and artifacts:
              - returns information about the latest attempt for artifacts
              - returns all metadata across all attempts
            Otherwise, returns information about metadata and artifacts for that
            attempt only.
            NOTE: For older versions of Metaflow (pre 2.4.0), the attempt for
            metadata is not known; in that case, all metadata is returned (as
            if None was passed in).

        Return
        ------
            object or list :
                Depending on the call, the type of object return varies
        '''
        obj_order = {
            'root': 0,
            'flow': 1,
            'run': 2,
            'step': 3,
            'task': 4,
            'artifact': 5,
            'metadata': 6,
            'self': 7}
        type_order = obj_order.get(obj_type)
        sub_order = obj_order.get(sub_type)

        if type_order is None:
            raise MetaflowInternalError(msg='Cannot find type %s' % obj_type)
        if type_order > 5:
            raise MetaflowInternalError(msg='Type %s is not allowed' % obj_type)

        if sub_order is None:
            raise MetaflowInternalError(msg='Cannot find subtype %s' % sub_type)

        if type_order >= sub_order:
            raise MetaflowInternalError(msg='Subtype %s not allowed for %s' % (sub_type, obj_type))

        # Metadata is always only at the task level
        if sub_type == 'metadata' and obj_type != 'task':
            raise MetaflowInternalError(msg='Metadata can only be retrieved at the task level')

        if attempt is not None:
            try:
                attempt_int = int(attempt)
                if attempt_int < 0:
                    raise ValueError("Attempt can only be positive")
            except ValueError:
                raise ValueError("Attempt can only be a positive integer")
        else:
            attempt_int = None

        pre_filter = cls._get_object_internal(
            obj_type, type_order, sub_type, sub_order, filters, attempt_int, *args)
        if attempt_int is None or sub_order != 6:
            # If no attempt or not for metadata, just return as is
            return pre_filter
        return MetadataProvider._reconstruct_metadata_for_attempt(
            pre_filter, attempt_int)

    def _all_obj_elements(self, tags=None, sys_tags=None):
        user = get_username()
        return {
            'flow_id': self._flow_name,
            'user_name': user,
            'tags': list(tags) if tags else [],
            'system_tags': list(sys_tags) if sys_tags else [],
            'ts_epoch': int(round(time.time() * 1000))}

    def _flow_to_json(self):
        # No need to store tags, sys_tags or username at the flow level
        # since runs are the top level logical concept, which is where we
        # store tags, sys_tags and username
        return {
            'flow_id': self._flow_name,
            'ts_epoch': int(round(time.time() * 1000))}

    def _run_to_json(self, run_id=None, tags=None, sys_tags=None):
        if run_id is not None:
            d = {'run_number': run_id}
        else:
            d = {}
        d.update(self._all_obj_elements(tags, sys_tags))
        return d

    def _step_to_json(self, run_id, step_name, tags=None, sys_tags=None):
        d = {
            'run_number': run_id,
            'step_name': step_name}
        d.update(self._all_obj_elements(tags, sys_tags))
        return d

    def _task_to_json(self, run_id, step_name, task_id=None, tags=None, sys_tags=None):
        d = {
            'run_number': run_id,
            'step_name': step_name}
        if task_id is not None:
            d['task_id'] = task_id
        d.update(self._all_obj_elements(tags, sys_tags))
        return d

    def _object_to_json(
            self, obj_type, run_id=None, step_name=None, task_id=None, tags=None, sys_tags=None):
        if obj_type == 'task':
            return self._task_to_json(run_id, step_name, task_id, tags, sys_tags)
        if obj_type == 'step':
            return self._step_to_json(run_id, step_name, tags, sys_tags)
        if obj_type == 'run':
            return self._run_to_json(run_id, tags, sys_tags)
        return self._flow_to_json()

    def _artifacts_to_json(self, run_id, step_name, task_id, attempt_id, artifacts):
        result = []
        for art in artifacts:
            d = {
                'run_number': run_id,
                'step_name': step_name,
                'task_id': task_id,
                'attempt_id': attempt_id,
                'name': art.name,
                'content_type': art.type,
                'type': 'metaflow.artifact',
                'sha': art.sha,
                'ds_type': art.ds_type,
                'location': art.url if art.url else ':root:%s' % art.ds_root}
            d.update(self._all_obj_elements(self.sticky_tags, self.sticky_sys_tags))
            result.append(d)
        return result

    def _metadata_to_json(self, run_id, step_name, task_id, metadata):
        user = get_username()
        return [{
            'flow_id': self._flow_name,
            'run_number': run_id,
            'step_name': step_name,
            'task_id': task_id,
            'field_name': datum.field,
            'type': datum.type,
            'value': datum.value,
            'tags': list(set(datum.tags)) if datum.tags else [],
            'user_name': user,
            'ts_epoch': int(round(time.time() * 1000))} for datum in metadata]

    def _tags(self):
        env = self._environment.get_environment_info()
        tags = [
            resolve_identity(),
            'runtime:' + env['runtime'],
            'python_version:' + env['python_version_code'],
            'date:' + datetime.utcnow().strftime('%Y-%m-%d')]
        if env['metaflow_version']:
            tags.append('metaflow_version:' + env['metaflow_version'])
        if 'metaflow_r_version' in env:
            tags.append('metaflow_r_version:' + env['metaflow_r_version'])
        if 'r_version_code' in env:
            tags.append('r_version:' + env['r_version_code'])
        return tags

    def _register_code_package_metadata(self, run_id, step_name, task_id, attempt):
        metadata = []
        code_sha = os.environ.get('METAFLOW_CODE_SHA')
        code_url = os.environ.get('METAFLOW_CODE_URL')
        code_ds = os.environ.get('METAFLOW_CODE_DS')
        if code_sha:
            metadata.append(MetaDatum(
                field='code-package',
                value=json.dumps({'ds_type': code_ds, 'sha': code_sha, 'location': code_url}),
                type='code-package',
                tags=["attempt_id:{0}".format(attempt)]))
        # We don't tag with attempt_id here because not readily available; this
        # is ok though as this doesn't change from attempt to attempt.
        if metadata:
            self.register_metadata(run_id, step_name, task_id, metadata)

    @staticmethod
    def _apply_filter(elts, filters):
        if filters is None:
            return elts
        starting_point = elts
        result = []
        for key, value in filters.items():
            if key == 'any_tags':
                for obj in starting_point:
                    if value in obj.get('tags', []) or value in obj.get('system_tags', []):
                        result.append(obj)
            if key == 'tags':
                for obj in starting_point:
                    if value in obj.get('tags', []):
                        result.append(obj)
            if key == 'system_tags':
                for obj in starting_point:
                    if value in obj.get('system_tags', []):
                        result.append(obj)
            starting_point = result
            result = []
        return starting_point

    @staticmethod
    def _reconstruct_metadata_for_attempt(all_metadata, attempt_id):
        have_all_attempt_id = True
        attempts_start = {}
        post_filter = []
        for v in all_metadata:
            if v['field_name'] == 'attempt':
                attempts_start[int(v['value'])] = v['ts_epoch']
            all_tags = v.get('tags')
            if all_tags is None:
                all_tags = []
            for t in all_tags:
                match_result = attempt_id_re.match(t)
                if match_result:
                    if int(match_result.group(1)) == attempt_id:
                        post_filter.append(v)
                    break
            else:
                # We didn't encounter a match for attempt_id
                have_all_attempt_id = False

        if not have_all_attempt_id:
            # We reconstruct base on the attempts_start
            start_ts = attempts_start.get(attempt_id, -1)
            if start_ts < 0:
                return [] # No metadata since the attempt hasn't started
            # Doubt we will be using Python in year 3000
            end_ts = attempts_start.get(attempt_id + 1, 32503680000000)
            post_filter = [v for v in all_metadata
                if v['ts_epoch'] >= start_ts and v['ts_epoch'] < end_ts]

        return post_filter

    def __init__(self, environment, flow, event_logger, monitor):
        self._task_id_seq = -1
        self.sticky_tags = set()
        self.sticky_sys_tags = set()
        self._flow_name = flow.name
        self._event_logger = event_logger
        self._monitor = monitor
        self._environment = environment
        self._runtime = os.environ.get(
            'METAFLOW_RUNTIME_NAME', 'dev')
        self.add_sticky_tags(sys_tags=self._tags())
