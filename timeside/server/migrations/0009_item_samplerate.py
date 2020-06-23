# Generated by Django 2.2 on 2020-05-26 08:38

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('timeside_server', '0008_auto_fields_help_texts'),
    ]

    operations = [
        migrations.AddField(
            model_name='item',
            name='samplerate',
            field=models.IntegerField(
                blank=True,
                help_text='Sampling rate of audio source file.',
                null=True,
                verbose_name='sampling rate'
                ),
        ),        
    ]