import logging

logger = logging.getLogger('tasks_app.youtube')


def run_yt_import(job_pk: int, playlist_id: str, subject_pk, exam_type: str, coach_pk: int) -> None:
    """Django-Q task: import or sync a YouTube playlist."""
    from tasks_app.models import YouTubeImportJob
    from tasks_app.services.youtube_playlist_importer import (
        sync_playlist, PlaylistNotFound, YouTubeAPIError,
    )

    try:
        job = YouTubeImportJob.objects.get(pk=job_pk)
    except YouTubeImportJob.DoesNotExist:
        logger.error('YouTubeImportJob %s not found', job_pk)
        return

    job.status = YouTubeImportJob.STATUS_RUNNING
    job.save(update_fields=['status', 'updated_at'])

    try:
        from django.contrib.auth import get_user_model
        coach = get_user_model().objects.get(pk=coach_pk)

        subject = None
        if subject_pk is not None:
            from exams_app.models import Subject
            subject = Subject.objects.get(pk=int(subject_pk))

        def _progress(msg: str) -> None:
            job.progress_msg = msg[:255]
            job.save(update_fields=['progress_msg', 'updated_at'])

        result = sync_playlist(playlist_id, subject, exam_type, coach, _progress)

        job.status      = YouTubeImportJob.STATUS_DONE
        job.playlist_pk = result['playlist_pk']
        job.result_msg  = result['summary']
        job.progress_msg = ''
        job.save(update_fields=['status', 'playlist_pk', 'result_msg', 'progress_msg', 'updated_at'])

    except PlaylistNotFound:
        job.status    = YouTubeImportJob.STATUS_FAILED
        job.error_msg = 'Liste bulunamadı veya gizli.'
        job.save(update_fields=['status', 'error_msg', 'updated_at'])
    except YouTubeAPIError as exc:
        job.status    = YouTubeImportJob.STATUS_FAILED
        job.error_msg = str(exc)
        job.save(update_fields=['status', 'error_msg', 'updated_at'])
    except Exception:
        logger.exception('Unexpected error in YouTube import job %s', job_pk)
        job.status    = YouTubeImportJob.STATUS_FAILED
        job.error_msg = 'Beklenmeyen bir hata oluştu.'
        job.save(update_fields=['status', 'error_msg', 'updated_at'])
