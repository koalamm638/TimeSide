# -*- coding: utf-8 -*-
#
# Copyright (c) 2007-2014 Guillaume Pellerin <yomguy@parisson.com>

# This file is part of TimeSide.

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.

# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import os

import numpy as np
from rest_framework import serializers
from rest_framework.reverse import reverse
# from builtins import str

from django.contrib.sites.models import Site

import timeside.server as ts
from timeside.server.models import _RUNNING, _PENDING

from jsonschema import ValidationError
import json


class ItemPlayableSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = ts.models.Item
        fields = ('player_url')

    def get_player_url(self, obj):
        current_site = Site.objects.get_current()
        return 'https://'                   \
            + current_site.domain           \
            + reverse('timeside-player')    \
            + '#item/' + str(obj.uuid)      \
            + '/'


class ItemListSerializer(ItemPlayableSerializer):

    player_url = serializers.SerializerMethodField()

    class Meta:
        model = ts.models.Item
        fields = ('uuid', 'url', 'title', 'description', 'player_url',
                  'source_file', 'source_url', 'mime_type')
        extra_kwargs = {
            'url': {'lookup_field': 'uuid'}
        }

    def get_url(self, obj):
        request = self.context['request']
        return reverse(
            'item-detail',
            kwargs={'uuid': obj.uuid},
            request=request
            )


class AudioUrlSerializer(serializers.Serializer):

    mp3 = serializers.URLField(read_only=True)
    ogg = serializers.URLField(read_only=True)

    def to_representation(self, instance):
        request = self.context['request']
        extensions = ['mp3', 'ogg']
        self.audio_url = {
            ext:
            reverse(
                'item-transcode-api',
                kwargs={'uuid': instance.uuid, 'extension': ext},
                request=request
                )
            for ext in extensions
            }
        return self.audio_url


class ItemSerializer(ItemPlayableSerializer):

    waveform_url = serializers.SerializerMethodField()
    player_url = serializers.SerializerMethodField()
    audio_url = AudioUrlSerializer(
        source='*',
        many=False,
        read_only=True,
    )
    annotation_tracks = serializers.HyperlinkedRelatedField(
        many=True,
        read_only=True,
        view_name='annotationtrack-detail',
        lookup_field='uuid'
    )
    analysis_tracks = serializers.HyperlinkedRelatedField(
        many=True,
        read_only=True,
        view_name='analysistrack-detail',
        lookup_field='uuid'
    )

    class Meta:
        model = ts.models.Item
        fields = ('uuid', 'url', 'player_url',
                  'title', 'description',
                  'source_file', 'source_url', 'mime_type',
                  'audio_url', 'audio_duration', 'external_uri',
                  'external_id',
                  'waveform_url',
                  'annotation_tracks',
                  'analysis_tracks',
                  'provider',
                  )
        extra_kwargs = {
            'url': {'lookup_field': 'uuid'},
            'provider': {'lookup_field': 'uuid'}
        }

        read_only_fields = ('url', 'uuid', 'audio_duration', 'player_url',)

    def get_url(self, obj):
        request = self.context['request']
        return reverse(
            'item-detail',
            kwargs={'uuid': obj.uuid},
            request=request
            )

    def get_waveform_url(self, obj):
        request = self.context['request']
        return reverse(
            'item-waveform',
            kwargs={'uuid': obj.uuid},
            request=request
            )


class WaveformSerializer(serializers.Serializer):
    """Populate waveform"""
    start = serializers.IntegerField(default=0)
    stop = serializers.IntegerField(default=-1)
    nb_pixels = serializers.IntegerField(min_value=0)
    min_values = serializers.ListField(
        child=serializers.FloatField(read_only=True)
        )
    max_values = serializers.ListField(
        child=serializers.FloatField(read_only=True)
        )
    time_values = serializers.ListField(
        child=serializers.IntegerField(read_only=True)
        )

    def to_representation(self, instance):
        request = self.context['request']
        self.start = float(request.GET.get('start', 0))
        self.stop = float(request.GET.get('stop', -1))
        self.nb_pixels = int(request.GET.get('nb_pixels', 1024))

        from .utils import get_or_run_proc_result
        result = get_or_run_proc_result('waveform_analyzer', item=instance)
        import h5py

        result_id = 'waveform_analyzer'
        wav_res = h5py.File(result.hdf5.path, 'r').get(result_id)

        duration = wav_res['audio_metadata'].attrs['duration']
        samplerate = wav_res['data_object'][
            'frame_metadata'].attrs['samplerate']

        if self.start < 0:
            self.start = 0
        if self.start > duration:
            raise serializers.ValidationError(
                "start must be less than duration")
        if self.stop == -1:
            self.stop = duration

        if self.stop > duration:
            self.stop = duration

        self.min_values = np.zeros(self.nb_pixels)
        self.max_values = np.zeros(self.nb_pixels)
        self.time_values = np.linspace(
            start=self.start,
            stop=self.stop,
            num=self.nb_pixels + 1,
            endpoint=True
            )

        sample_values = np.round(self.time_values * samplerate).astype('int')

        for i in range(self.nb_pixels):
            values = wav_res['data_object']['value'][
                sample_values[i]:sample_values[i + 1]]
            if values.size:
                self.min_values[i] = np.min(values)
                self.max_values[i] = np.max(values)

        return {'start': self.start,
                'stop': self.stop,
                'nb_pixels': self.nb_pixels,
                'time': self.time_values[0:-1],
                'min': self.min_values,
                'max': self.max_values}


class ItemWaveformSerializer(ItemSerializer):

    item_url = serializers.SerializerMethodField('get_url')
    waveform = WaveformSerializer(
        source='*',
        many=False,
        read_only=True,
        )
    waveform_image_url = serializers.SerializerMethodField()

    class Meta:
        model = ts.models.Item
        fields = ('item_url', 'title', 'waveform_url',
                  'waveform', 'waveform_image_url')
        # depth = 2
        # extra_kwargs

    def get_waveform_image_url(self, obj):
        request = self.context['request']
        from .utils import get_or_run_proc_result
        result = get_or_run_proc_result('waveform_analyzer', item=obj)
        return reverse('timeside-result-visualization',
                       kwargs={'uuid': result.uuid},
                       request=request)+'?id=waveform_analyzer'
    

class ItemAnalysisSerializer(serializers.HyperlinkedModelSerializer):

    analysis_url = serializers.SerializerMethodField()

    class Meta:
        model = ts.models.Item
        fields = ('uuid', 'url', 'analysis_url')
        extra_kwargs = {
            'url': {'lookup_field': 'uuid'}
        }

    def get_url(self, obj):
        request = self.context['request']
        return reverse('item-detail', kwargs={'uuid': obj.uuid},
                       request=request)

    def get_analysis_url(self, obj):
        analysis_url = self.get_url(obj) + 'analysis/'
        analysis = ts.models.Analysis.objects.all()

        return {a.title: analysis_url + a.uuid for a in analysis}


class ItemAnnotationsSerializer(serializers.HyperlinkedModelSerializer):

    annotations_url = serializers.SerializerMethodField()

    class Meta:
        model = ts.models.Item
        fields = ('uuid', 'url', 'annotations_url')
        extra_kwargs = {
            'url': {'lookup_field': 'uuid'}
        }

    def get_url(self, obj):
        request = self.context['request']
        return reverse(
            'item-detail',
            kwargs={'uuid': obj.uuid},
            request=request
            )

    def get_annotations_url(self, obj):
        annotations_url = self.get_url(obj) + 'annotations/'
        annotations = ts.models.Annotation.objects.all()

        return {a.title: annotations_url + a.uuid for a in annotations}


def get_result(item, preset, wait=True):
    # Get Result with preset and item
    try:
        result = ts.models.Result.objects.get(item=item, preset=preset)
        if not result.hdf5 or not os.path.exists(result.hdf5.path):
            # Result exists but there is no file (may have been deleted)
            result.delete()
            return get_result(item=item, preset=preset)
        return result
    except ts.models.Result.DoesNotExist:
        # Result does not exist
        # the corresponding task has to be created and run
        task, created = ts.models.Task.objects.get_or_create(
            experience=preset.get_single_experience(),
            selection=item.get_single_selection()
            )
        if created:
            task.run(wait=False)
        elif task.status == _RUNNING:
            return 'Task Running'
        else:
            # Result does not exist but task exist and is done, draft or
            # pending
            task.status = _PENDING
            task.save()
        return 'Task Created and launched'


class ItemAnalysisResultSerializer(serializers.HyperlinkedModelSerializer):

    # analysis_url = serializers.HyperlinkedRelatedField(read_only=True,
    #
    #    )
    audio_duration = serializers.SerializerMethodField()
    result = serializers.SerializerMethodField()
    analysis_uuid = serializers.SerializerMethodField()

    class Meta:
        model = ts.models.Item
        fields = ('uuid', 'url', 'audio_duration',
                  'analysis_uuid', 'analysis_url', 'result')
        extra_kwargs = {
            'url': {'lookup_field': 'uuid'}
        }

    def get_url(self, obj):
        request = self.context['request']
        return reverse(
            'item-detail',
            kwargs={'uuid': obj.uuid},
            request=request
            )

    def get_analysis_uuid(self, obj):
        return self.lookup_url_kwarg['analysis_uuid']

    def get_analysis_url(self, obj):
        analysis_url = self.get_url(obj) + 'analysis/'
        analysis_uuid = self.get_analysis_uuid(obj)

        return analysis_url + analysis_uuid

    def get_audio_duration(self, obj):
        return obj.get_audio_duration()

    def get_result(self, obj):
        analysis_uuid = self.get_analysis_uuid(obj)
        try:
            analysis, c = ts.models.Analysis.objects.get(uuid=analysis_uuid)
        except ts.models.Analysis.DoesNotExist:
            return {'Unknown analysis': analysis_uuid}

        preset = analysis.preset

        result = get_result(item=obj, preset=preset)
        if isinstance(result, ts.models.Result):
            res_msg = result.uuid
        else:
            res_msg = result
        return {'analysis': analysis.uuid,
                'item': item.uuid}


class SelectionSerializer(serializers.HyperlinkedModelSerializer):

    class Meta:
        model = ts.models.Selection
        fields = ('title', 'uuid', 'url', 'items', 'selections', 'author')
        extra_kwargs = {
            'url': {'lookup_field': 'uuid'},
            'selections': {'lookup_field': 'uuid'},
            'items': {'lookup_field': 'uuid'},
            'author': {'lookup_field': 'username'}
        }
        read_only_fields = ('url', 'uuid', 'title')

    def update(self, instance, validated_data):
        instance.author = validated_data.get('title', instance.author)
        instance.title = validated_data.get('title', instance.title)
        selections = validated_data.get('selections')
        if selections:
            for selection in selections:
                instance.selections.add(selection)
        items = validated_data.get('items')
        if items:
            for item in items:
                instance.items.add(item)
        instance.save()

        return instance


class ExperienceSerializer(serializers.HyperlinkedModelSerializer):

    class Meta:
        model = ts.models.Experience
        fields = ('title', 'uuid', 'url', 'presets', 'is_public', 'author')
        extra_kwargs = {
            'url': {'lookup_field': 'uuid'},
            'presets': {'lookup_field': 'uuid'},
            'author': {'lookup_field': 'username'}
        }
        read_only_fields = ('url', 'uuid',)


class ProcessorSerializer(serializers.HyperlinkedModelSerializer):

    pid = serializers.ChoiceField(choices=ts.models.get_processor_pids())
    parameters_schema = serializers.SerializerMethodField()

    class Meta:
        model = ts.models.Processor
        fields = ('name', 'pid', 'url', 'version', 'parameters_schema')
        extra_kwargs = {
            'url': {'lookup_field': 'pid'}
        }

    def get_parameters_schema(self, obj):
        return obj.get_parameters_schema()


class ProcessorListSerializer(serializers.HyperlinkedModelSerializer):

    pid = serializers.ChoiceField(choices=ts.models.get_processor_pids())

    class Meta:
        model = ts.models.Processor
        fields = ('name', 'pid', 'url', 'version')
        extra_kwargs = {
            'url': {'lookup_field': 'pid'}
        }


class ParametersSchemaSerializer(serializers.HyperlinkedModelSerializer):

    parameters_schema = serializers.SerializerMethodField()

    class Meta:
        model = ts.models.Processor
        fields = ('parameters_schema',)

    def get_parameters_schema(self, obj):
        return obj.get_parameters_schema()


class ParametersDefaultSerializer(serializers.HyperlinkedModelSerializer):

    parameters_default = serializers.SerializerMethodField()

    class Meta:
        model = ts.models.Processor
        fields = ('parameters_default',)

    def get_parameters_default(self, obj):
        return obj.get_parameters_default()


class SubProcessorSerializer(serializers.HyperlinkedModelSerializer):

    class Meta:
        model = ts.models.SubProcessor
        fields = ('url', 'name', 'processor', 'sub_processor_id')
        extra_kwargs = {
            'url': {'lookup_field': 'sub_processor_id'},
            'processor': {'lookup_field': 'pid'}
        }


class PresetSerializer(serializers.HyperlinkedModelSerializer):

    class Meta:
        model = ts.models.Preset
        fields = ('url', 'uuid', 'processor', 'parameters')
        extra_kwargs = {
            'url': {'lookup_field': 'uuid'},
            'processor': {'lookup_field': 'pid'}
        }
        read_only_fields = ('url', 'uuid',)

    def validate(self, data):

        import timeside.core
        proc = timeside.core.get_processor(data['processor'].pid)
        if proc.type == 'analyzer':
            processor = proc()
            default_params = processor.get_parameters()
            default_msg = "Defaut parameters:\n%s" % default_params

            if not data['parameters']:
                data['parameters'] = '{}'
            try:
                processor.validate_parameters(json.loads(data['parameters']))
            except ValidationError as e:
                msg = '\n'.join([str(e), default_msg])
                raise serializers.ValidationError(msg)
            except KeyError as e:
                msg = '\n'.join(['KeyError :' + str(e), default_msg])
                raise serializers.ValidationError(msg)

            processor = proc(**json.loads(data['parameters']))
            data['parameters'] = json.dumps(processor.get_parameters())
        return data


class ResultSerializer(serializers.HyperlinkedModelSerializer):

    class Meta:
        model = ts.models.Result
        fields = ('uuid', 'url', 'item', 'preset', 'status',
                  'hdf5', 'file', 'run_time')
        extra_kwargs = {
            'url': {'lookup_field': 'uuid'},
            'item': {'lookup_field': 'uuid'},
            'preset': {'lookup_field': 'uuid'}
        }
        read_only_fields = ('uuid',)


class ResultVisualizationSerializer(serializers.BaseSerializer):
    """
    A read-only serializer that deals with subprocessor results
    """

    def to_representation(self, obj):
        subprocessor_id = self.context.get('request').query_params.get('id')

        start = float(self.context.get('request').query_params.get('start', 0))
        stop = float(self.context.get('request').query_params.get('stop', -1))
        width = int(self.context.get(
            'request').query_params.get('width', 1024))
        height = int(self.context.get(
            'request').query_params.get('height', 128))

        import h5py
        hdf5_result = h5py.File(obj.hdf5.path, 'r').get(subprocessor_id)
        from timeside.core.analyzer import AnalyzerResult
        result = AnalyzerResult().from_hdf5(hdf5_result)
        duration = hdf5_result['audio_metadata'].attrs['duration']

        if start < 0:
            start = 0
        if start > duration:
            raise serializers.ValidationError(
                "start must be less than duration")
        if stop == -1:
            stop = duration

            if stop > duration:
                stop = duration

        if True:
            # if result.data_object.y_value.size:

            import StringIO
            pil_image = result._render_PIL(
                size=(width, height), dpi=80, xlim=(start, stop))
            image_buffer = StringIO.StringIO()
            pil_image.save(image_buffer, 'PNG')
            return image_buffer.getvalue()
        else:
            return result.to_json()


class TaskSerializer(serializers.HyperlinkedModelSerializer):

    class Meta:
        model = ts.models.Task
        fields = ('url', 'uuid', 'experience',
                  'selection', 'status', 'author', 'item')
        extra_kwargs = {
            'url': {'lookup_field': 'uuid'},
            'experience': {'lookup_field': 'uuid'},
            'selection': {'lookup_field': 'uuid'},
            'author': {'lookup_field': 'username'},
            'item': {'lookup_field': 'uuid'}
            }


class UserSerializer(serializers.HyperlinkedModelSerializer):

    class Meta:
        model = ts.models.User
        fields = ('url', 'username', 'first_name', 'last_name')
        extra_kwargs = {
            'url': {'lookup_field': 'username'}
        }


class AnalysisSerializer(serializers.HyperlinkedModelSerializer):

    parameters_schema = serializers.JSONField()

    class Meta:
        model = ts.models.Analysis
        fields = ('url', 'uuid',
                  'title', 'description',
                  'preset', 'sub_processor',
                  'parameters_schema')
        extra_kwargs = {
            'url': {'lookup_field': 'uuid'},
            'preset': {'lookup_field': 'uuid'},
            'sub_processor': {'lookup_field': 'sub_processor_id'}
        }
        read_only_fields = ('url', 'uuid',)


class AnalysisTrackSerializer(serializers.HyperlinkedModelSerializer):

    result_url = serializers.SerializerMethodField()
    parameters_schema = serializers.SerializerMethodField()
    parameters_default = serializers.SerializerMethodField()
    parametrizable = serializers.SerializerMethodField()

    class Meta:
        model = ts.models.AnalysisTrack
        fields = ('url', 'uuid',
                  'title', 'description',
                  'analysis', 'item', 'result_url',
                  'parameters_schema', 'parameters_default',
                  'parametrizable')
        extra_kwargs = {
            'url': {'lookup_field': 'uuid'},
            'item': {'lookup_field': 'uuid'},
            'analysis': {'lookup_field': 'uuid'},
        }
        read_only_fields = ('url', 'uuid',)

    def create(self, validated_data):
        item = validated_data['item']
        analysis = validated_data['analysis']

        preset = analysis.preset

        result = get_result(item=item, preset=preset)

        # if isinstance(result, Result):
        #    res_msg = result.uuid
        # else:
        #    res_msg = result
        # return {'analysis': analysis.uuid,
        #        'item': item.uuid}

        return super(AnalysisTrackSerializer, self).create(validated_data)

    def get_result_uuid(self, obj):
        result = get_result(item=obj.item, preset=obj.analysis.preset)
        if isinstance(result, ts.models.Result):
            self._result_uuid = result.uuid
            return result.uuid
        else:
            self._result_uuid = None
        return self._result_uuid

    def get_result_url(self, obj):
        self.get_result_uuid(obj)
        if self._result_uuid is not None:
            url_kwargs = {'uuid': self._result_uuid}
            request = self.context['request']
            parameters = '?id=%s' % obj.analysis.sub_processor
            return reverse(
                'timeside-result-visualization',
                kwargs=url_kwargs,
                request=request
                ) + parameters
        else:
            return 'Task running'

    def get_parameters_schema(self, obj):
        return obj.analysis.parameters_schema

    def get_parameters_default(self, obj):
        return obj.analysis.preset.processor.get_parameters_default()

    def get_parametrizable(self, obj):
        schema = self.get_parameters_schema(obj)
        if not schema or not schema['properties']:
            return False
        # TODO : Manage User permission to parametrize Analysis
        return True

    # def get_url(self, obj, view_name, request, format):
    # url_kwargs = {
    # 'item_uuid': obj.item.uuid,
    # 'analysis_uuid': obj.analysis.uuid.pk
    # }
    # return reverse(view_name, kwargs=url_kwargs, request=request,
    # format=format)


class AnnotationSerializer_inTrack(serializers.HyperlinkedModelSerializer):

    class Meta:
        model = ts.models.Annotation
        fields = ('url', 'uuid',
                  'title', 'description',
                  'start_time', 'stop_time')
        extra_kwargs = {
            'url': {'lookup_field': 'uuid'},
            'track': {'lookup_field': 'uuid'},
        }
        read_only_fields = ('url', 'uuid',)


class AnnotationSerializer(serializers.HyperlinkedModelSerializer):

    class Meta:
        model = ts.models.Annotation
        fields = ('url', 'uuid', 'track',
                  'title', 'description',
                  'start_time', 'stop_time')
        extra_kwargs = {
            'url': {'lookup_field': 'uuid'},
            'track': {'lookup_field': 'uuid'},
        }
        read_only_fields = ('uuid',)


class AnnotationTrackSerializer(serializers.HyperlinkedModelSerializer):

    annotations = AnnotationSerializer_inTrack(many=True, read_only=True)

    class Meta:
        model = ts.models.AnnotationTrack
        fields = ('url', 'uuid', 'item',
                  'title', 'description',
                  'author',
                  'is_public',
                  'overlapping',
                  'annotations')
        extra_kwargs = {
            'url': {'lookup_field': 'uuid'},
            'item': {'lookup_field': 'uuid'},
            'author': {'lookup_field': 'username'},
            'annotations': {'lookup_field': 'uuid'},
        }
        read_only_fields = ('uuid',)


class ProviderSerializer(serializers.HyperlinkedModelSerializer):

    class Meta:
        model = ts.models.Provider
        fields = ('pid', 'uuid', 'source_access')
        read_only_fields = ('uuid',)
