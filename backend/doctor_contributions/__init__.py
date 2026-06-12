"""Parent-contributions domain (DOC-5): parent-submitted doctors + recommendations.

The first ORM-mapped domain in the backend (see :mod:`.orm`). Owns the
write-path for the doctor directory — parents propose clinicians we are missing
and leave recommendations — plus the superadmin moderation surface. Approved
contributions are mixed into the public catalogue by
:mod:`backend.doctor_catalog`; pending/rejected ones are never public.
"""
