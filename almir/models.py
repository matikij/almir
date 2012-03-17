"""Models generated from bacula-dir-postgresql 5.0.2"""
import datetime
import stat

from jinja2 import Markup
from sqlalchemy import Column
from sqlalchemy.orm import relationship, noload, joinedload
from sqlalchemy.sql.expression import desc
from sqlalchemy.sql import functions as func
from webhelpers.date import distance_of_time_in_words

from almir.meta import Base, ModelMixin, DBSession
from almir.lib.sqlalchemy_custom_types import BaculaDateTime
from almir.lib.filters import nl2br, yesno
from almir.lib.bacula_base64 import decode_base64
from almir.lib.bconsole import BConsole


# defined in bacula/src/plugins/fd/fd_common.h
LEVELS = {
    'F': 'Full',
    'I': 'Incremental',  # since last backup
    'D': 'Differential',  # since last full backup
}
TYPES = {
    'B': 'Backup',
    'R': 'Restore',
}
# TODO: parse from bacula/bacula/src/lib/util.c
VOLUME_STATUS_SEVERITY = {
    "Append": 'ok',
    "Archive": 'unknown',
    "Disabled": 'unknown',
    "Full": 'unknown',
    "Used": 'unknown',
    "Cleaning": 'unknown',
    "Purged": 'unknown',
    "Recycle": 'unknown',
    "Read-Only": 'unknown',
    "Error": 'error',
}


class Status(ModelMixin, Base):
    """
        Column     |     Type     | Modifiers
    ---------------+--------------+-----------
     jobstatus     | character(1) | not null
     jobstatuslong | text         |
     severity      | integer      |

    Indexes:
        "status_pkey" PRIMARY KEY, btree (jobstatus)

    """


class Client(ModelMixin, Base):
    """
        Column     |   Type   |                         Modifiers
    ---------------+----------+-----------------------------------------------------------
     clientid      | integer  | not null default nextval('client_clientid_seq'::regclass)
     name          | text     | not null
     uname         | text     | not null
     autoprune     | smallint | default 0
     fileretention | bigint   | default 0
     jobretention  | bigint   | default 0

    Indexes:
        "client_pkey" PRIMARY KEY, btree (clientid)
        "client_name_idx" UNIQUE, btree (name)

    """

    @classmethod
    def object_detail(cls, id_):
        id_ = int(id_)
        d = super(Client, cls).object_detail(id_)
        # TODO: write this with subqueries
        d.update({
            'jobs': Job.query.filter(Job.clientid == id_).order_by(desc(Job.schedtime)).limit(50),
            'num_jobs': Job.query.count(),
            'last_successful_job': Job.query.filter(Job.clientid == id_).filter(Job.jobstatus == 'T').order_by(desc(Job.starttime)).first(),
            'total_size_backups': cls.format_byte_size(Job.query.with_entities(func.sum(Job.jobbytes)).filter(Job.clientid == id_).scalar()),
        })
        return d

    @classmethod
    def objects_list(cls):
        # SELECT client.clientid, job_bytes, max_job FROM client
        # LEFT JOIN (SELECT job.clientid, SUM(job.jobbytes) AS job_bytes FROM job
        # GROUP BY job.clientid) AS vsota ON vsota.clientid = client.clientid
        # LEFT JOIN (SELECT job.clientid, MAX(job.schedtime) AS max_job FROM job
        # GROUP BY job.clientid) AS last_job ON last_job.clientid = client.clientid;
        sum_stmt = Job.query\
            .with_entities(Job.clientid, func.sum(Job.jobbytes).label('job_sumvolbytes'))\
            .group_by(Job.clientid)\
            .subquery('stmt_sub')
        last_stmt = Job.query\
            .with_entities(Job.clientid, func.max(Job.starttime).label('job_maxschedtime')).filter(Job.jobstatus == 'T')\
            .group_by(Job.clientid)\
            .subquery('stmt_max')
        d = {}
        d['objects'] = cls.query.with_entities(Client, 'job_sumvolbytes', 'job_maxschedtime', func.count(Job.jobid).label('num_jobs'))\
            .outerjoin(Job)\
            .outerjoin(sum_stmt, sum_stmt.c.clientid == Client.clientid)\
            .outerjoin(last_stmt, last_stmt.c.clientid == Client.clientid)\
            .group_by(cls)\
            .all()

        # ugly hack since sqlite returns strings for job_maxschedtime
        # TODO: report upstream to sqlalchemy
        if DBSession.bind.dialect.name == 'sqlite':
            def convert_datetime(l):
                l.job_maxschedtime = datetime.datetime.strptime(l.job_maxschedtime, '%Y-%m-%d %H:%M:%S')
                return l
            d['objects'] = map(convert_datetime, d['objects'])
        return d

    def url(self, request):
        return request.route_url('client_detail', id=self.clientid)

    def render_name(self, request):
        return {'text': self.name, 'href': self.url(request)}

    def render_jobretention(self, request):
        # jobretention is integer of seconds
        return {'text': distance_of_time_in_words(self.jobretention)}

    def render_fileretention(self, request):
        # fileretention is integer of seconds
        return {'text': distance_of_time_in_words(self.fileretention)}

    def render_autoprune(self, request):
        return {'text': yesno(self.autoprune)}


class Job(ModelMixin, Base):
    """
         Column      |            Type             |                      Modifiers
    -----------------+-----------------------------+-----------------------------------------------------
     jobid           | integer                     | not null default nextval('job_jobid_seq'::regclass)
     job             | text                        | not null
     name            | text                        | not null
     type            | character(1)                | not null
     level           | character(1)                | not null
     clientid        | integer                     | default 0
     jobstatus       | character(1)                | not null
     schedtime       | timestamp without time zone |
     starttime       | timestamp without time zone |
     endtime         | timestamp without time zone |
     realendtime     | timestamp without time zone |
     jobtdate        | bigint                      | default 0
     volsessionid    | integer                     | default 0
     volsessiontime  | integer                     | default 0
     jobfiles        | integer                     | default 0
     jobbytes        | bigint                      | default 0
     readbytes       | bigint                      | default 0
     joberrors       | integer                     | default 0
     jobmissingfiles | integer                     | default 0
     poolid          | integer                     | default 0
     filesetid       | integer                     | default 0
     priorjobid      | integer                     | default 0
     purgedfiles     | smallint                    | default 0
     hasbase         | smallint                    | default 0
     hascache        | smallint                    | default 0
     reviewed        | smallint                    | default 0
     comment         | text                        |

    Indexes:
        "job_pkey" PRIMARY KEY, btree (jobid)
        "job_name_idx" btree (name)
    """

    schedtime = Column('schedtime', BaculaDateTime())
    starttime = Column('starttime', BaculaDateTime())
    endtime = Column('endtime', BaculaDateTime())
    realendtime = Column('realendtime', BaculaDateTime())

    @property
    def level_name(self):
        return LEVELS[self.level]

    @property
    def type_name(self):
        return TYPES[self.type]

    @property
    def status_name(self):
        return self.status.jobstatuslong

    @property
    def status_color(self):
        """Color of the job depending on status"""
        if self.status.severity < 15:
            return "ok"
        elif self.status.severity > 15:
            return "error"
        else:
            return "unknown"

    status = relationship(
        "Status",
        lazy="joined",
        primaryjoin="Job.jobstatus==Status.jobstatus",
        foreign_keys="Job.jobstatus",
    )
    client = relationship(
        "Client",
        lazy="joined",
        primaryjoin="Job.clientid==Client.clientid",
        foreign_keys="Job.clientid",
        backref='jobs',
    )
    pool = relationship(
        "Pool",
        lazy="joined",
        primaryjoin="Job.poolid==Pool.poolid",
        foreign_keys="Job.poolid",
    )
    jobmedias = relationship(
        "JobMedia",
        lazy="joined",
        primaryjoin="Job.jobid==JobMedia.jobid",
        foreign_keys="JobMedia.jobid",
        backref="jobs",
    )
    logs = relationship(
        "Log",
        lazy="joined",
        primaryjoin="Job.jobid==Log.jobid",
        foreign_keys="Log.jobid",
        backref="job",
    )
    files = relationship(
        "File",
        lazy="joined",
        primaryjoin="Job.jobid==File.jobid",
        foreign_keys="File.jobid",
        backref="job",
    )

    @classmethod
    def get_upcoming(cls):
        return BConsole().get_upcoming_jobs()

    @classmethod
    def get_running(cls):
        d = super(Job, cls).objects_list()
        return d['objects'].options(noload('*'), joinedload(cls.status), joinedload(cls.client))\
                           .join('status')\
                           .filter(Status.severity == 15)\
                           .order_by(desc(Job.starttime))\
                           .limit(50)

    @classmethod
    def get_last(cls):
        d = super(Job, cls).objects_list()
        return d['objects'].options(noload('*'), joinedload(cls.status), joinedload(cls.client))\
                           .join('status')\
                           .filter(Status.severity != 15)\
                           .order_by(desc(Job.schedtime))\
                           .limit(5)

    @classmethod
    def objects_list(cls):
        d = super(Job, cls).objects_list()
        d['objects'] = d['objects'].order_by(desc(Job.starttime)).limit(50)
        return d

    def url(self, request):
        return request.route_url('job_detail', id=self.jobid)

    def render_client_name(self, request):
        if self.client:
            return self.client.render_name(request)

    def render_volume_name(self, request):
        if self.jobmedias:
            return (jobmedia.medias.render_volumename(request) for jobmedia in self.jobmedias)
        else:
            return []

    def render_pool_name(self, request):
        if self.pool:
            return self.pool.render_name(request)

    def render_duration(self, request):
        if self.starttime and self.endtime:
            return self.render_distance_of_time_in_words(self.starttime, self.endtime)

    def render_jobbytes(self, request):
        return {'text': self.format_byte_size(self.jobbytes)}

    def render_joberrors(self, request):
        d = {'text': self.joberrors}
        if self.joberrors:
            d['cssclass'] = 'error'
        return d

    def render_starttime(self, request):
        return self.render_distance_of_time_in_words(self.starttime)


class Media(ModelMixin, Base):
    """
          Column      |            Type             |                        Modifiers
    ------------------+-----------------------------+---------------------------------------------------------
     actiononpurge    | smallint                    | default 0
     comment          | text                        |
     deviceid         | integer                     | default 0
     enabled          | smallint                    | default 1
     endblock         | bigint                      | default 0
     endfile          | integer                     | default 0
     firstwritten     | timestamp without time zone |
     inchanger        | smallint                    | default 0
     initialwrite     | timestamp without time zone |
     labeldate        | timestamp without time zone |
     labeltype        | integer                     | default 0
     lastwritten      | timestamp without time zone |
     locationid       | integer                     | default 0
     maxvolbytes      | bigint                      | default 0
     maxvolfiles      | integer                     | default 0
     maxvoljobs       | integer                     | default 0
     mediaaddressing  | smallint                    | default 0
     mediaid          | integer                     | not null default nextval('media_mediaid_seq'::regclass)
     mediatypeid      | integer                     | default 0
     mediatype        | text                        | not null
     poolid           | integer                     | default 0
     recyclecount     | integer                     | default 0
     recyclepoolid    | integer                     | default 0
     recycle          | smallint                    | default 0
     scratchpoolid    | integer                     | default 0
     slot             | integer                     | default 0
     storageid        | integer                     | default 0
     volblocks        | integer                     | default 0
     volbytes         | bigint                      | default 0
     volcapacitybytes | bigint                      | default 0
     volerrors        | integer                     | default 0
     volfiles         | integer                     | default 0
     voljobs          | integer                     | default 0
     volmounts        | integer                     | default 0
     volparts         | integer                     | default 0
     volreadtime      | bigint                      | default 0
     volretention     | bigint                      | default 0
     volstatus        | text                        | not null
     volumename       | text                        | not null
     voluseduration   | bigint                      | default 0
     volwrites        | integer                     | default 0
     volwritetime     | bigint                      | default 0

    Indexes:
        "media_pkey" PRIMARY KEY, btree (mediaid)
        "media_volumename_id" UNIQUE, btree (volumename)
    Check constraints:
        "media_volstatus_check" CHECK (volstatus = ANY (ARRAY['Full'::text, 'Archive'::text, 'Append'::text, 'Recycle'::text, 'Purged'::text, 'Read-Only'::text, 'Disabled'::text, 'Error'::text, 'Busy'::text, 'Used'::text, 'Cleaning'::text, 'Scratch'::text]))

    """
    firstwritten = Column('firstwritten', BaculaDateTime())
    lastwritten = Column('lastwritten', BaculaDateTime())
    labeldate = Column('labeldate', BaculaDateTime())
    initialwrite = Column('initialwrite', BaculaDateTime())

    storage = relationship(
        "Storage",
        lazy="joined",
        primaryjoin="Media.storageid==Storage.storageid",
        foreign_keys="Media.storageid",
        backref="medias",
    )

    pool = relationship(
        "Pool",
        lazy="joined",
        primaryjoin="Media.poolid==Pool.poolid",
        foreign_keys="Media.poolid",
        backref="medias",
    )

    # TODO: mediatype

    def url(self, request):
        return request.route_url('volume_detail', id=self.mediaid)

    def render_volumename(self, request):
        return {'text': self.volumename, 'href': self.url(request)}

    def render_volcapacitybytes(self, request):
        return {'text': self.format_byte_size(self.volcapacitybytes)}

    def render_volbytes(self, request):
        return {'text': self.format_byte_size(self.volbytes)}

    def render_maxvolbytes(self, request):
        return {'text': self.format_byte_size(self.maxvolbytes)}

    def render_volretention(self, request):
        # volretention is integer of seconds
        return {'text': distance_of_time_in_words(self.volretention)}

    def render_volstatus(self, request):
        return {'text': self.volstatus, 'cssclass': VOLUME_STATUS_SEVERITY[self.volstatus]}

    def render_storage_name(self, request):
        if self.storage:
            return self.storage.render_name(request)

    def render_pool_name(self, request):
        if self.pool:
            return self.pool.render_name(request)

    def render_enabled(self, request):
        return {'text': yesno(self.enabled)}

    def render_recycled(self, request):
        return {'text': yesno(self.enabled)}

    def render_expires(self, request):
        if self.firstwritten and self.volretention:
            return {'text': self.firstwritten + datetime.timedelta(seconds=self.volretention)}


class JobMedia(ModelMixin, Base):
    """
       Column   |  Type   |                           Modifiers
    ------------+---------+---------------------------------------------------------------
     jobmediaid | integer | not null default nextval('jobmedia_jobmediaid_seq'::regclass)
     jobid      | integer | not null
     mediaid    | integer | not null
     firstindex | integer | default 0
     lastindex  | integer | default 0
     startfile  | integer | default 0
     endfile    | integer | default 0
     startblock | bigint  | default 0
     endblock   | bigint  | default 0
     volindex   | integer | default 0

    Indexes:
        "jobmedia_pkey" PRIMARY KEY, btree (jobmediaid)
        "job_media_job_id_media_id_idx" btree (jobid, mediaid)
    """

    medias = relationship(
        "Media",
        lazy="joined",
        primaryjoin="JobMedia.mediaid==Media.mediaid",
        foreign_keys="JobMedia.mediaid",
        backref="jobmedias",
    )


class Storage(ModelMixin, Base):
    """
       Column    |  Type   |                          Modifiers
    -------------+---------+-------------------------------------------------------------
     storageid   | integer | not null default nextval('storage_storageid_seq'::regclass)
     name        | text    | not null
     autochanger | integer | default 0

    Indexes:
        "storage_pkey" PRIMARY KEY, btree (storageid)
    """

    @classmethod
    def objects_list(cls):
        d = super(Storage, cls).objects_list()
        d['objects'] = cls.query.with_entities(Storage,
                                               func.count(Media.mediaid).label('num_volumes'),
                                               #func.count(Job.jobid).label('num_jobs'),
                                               #func.count(Client.clientid).label('num_clients'),
                                               func.sum(Media.volbytes).label('total_backup_size'))\
                                .outerjoin('medias')\
                                .group_by(cls)
                                #.outerjoin('medias', 'jobmedias', 'jobs')\
        return d

    def url(self, request):
        return request.route_url('storage_detail', id=self.storageid)

    def render_name(self, request):
        return {'text': self.name, 'href': self.url(request)}


class Log(ModelMixin, Base):
    """
     Column  |            Type             |                      Modifiers
    ---------+-----------------------------+-----------------------------------------------------
     logid   | integer                     | not null default nextval('log_logid_seq'::regclass)
     jobid   | integer                     | not null
     time    | timestamp without time zone |
     logtext | text                        | not null

    Indexes:
        "log_pkey" PRIMARY KEY, btree (logid)
        "log_name_idx" btree (jobid)

    """
    time = Column('time', BaculaDateTime())

    def render_logtext(self, request):
        d = {}
        # sanitize logs
        log = self.logtext.strip('\\').strip().strip('\n')
        d['text'] = Markup(nl2br(log))
        if 'ERR' in self.logtext or 'Fatal error' in self.logtext:
            d['cssclass'] = 'error'
        return d


class Pool(ModelMixin, Base):
    """
           Column       |   Type   |                       Modifiers
    --------------------+----------+-------------------------------------------------------
     acceptanyvolume    | smallint | default 0
     actiononpurge      | smallint | default 0
     autoprune          | smallint | default 0
     enabled            | smallint | default 1
     labelformat        | text     | not null
     labeltype          | integer  | default 0
     maxvolbytes        | bigint   | default 0
     maxvolfiles        | integer  | default 0
     maxvoljobs         | integer  | default 0
     maxvols            | integer  | default 0
     migrationhighbytes | bigint   | default 0
     migrationlowbytes  | bigint   | default 0
     migrationtime      | bigint   | default 0
     name               | text     | not null
     nextpoolid         | integer  | default 0
     numvols            | integer  | default 0
     poolid             | integer  | not null default nextval('pool_poolid_seq'::regclass)
     pooltype           | text     |
     recyclepoolid      | integer  | default 0
     recycle            | smallint | default 0
     scratchpoolid      | integer  | default 0
     usecatalog         | smallint | default 0
     useonce            | smallint | default 0
     volretention       | bigint   | default 0
     voluseduration     | bigint   | default 0

    Indexes:
        "pool_pkey" PRIMARY KEY, btree (poolid)
        "pool_name_idx" btree (name)
    Check constraints:
        "pool_pooltype_check" CHECK (pooltype = ANY (ARRAY['Backup'::text, 'Copy'::text, 'Cloned'::text, 'Archive'::text, 'Migration'::text, 'Scratch'::text]))
    """

    def url(self, request):
        return request.route_url('pool_detail', id=self.poolid)

    def render_name(self, request):
        return {'text': self.name, 'href': self.url(request)}

    def render_enabled(self, request):
        return {'text': yesno(self.enabled)}

    def render_usecatalog(self, request):
        return {'text': yesno(self.usecatalog)}

    def render_useonce(self, request):
        return {'text': yesno(self.useonce)}

    def render_recycle(self, request):
        return {'text': yesno(self.recycle)}

    def render_autoprune(self, request):
        return {'text': yesno(self.autoprune)}

    def render_acceptanyvolume(self, request):
        return {'text': yesno(self.acceptanyvolume)}


class FileSet(ModelMixin, Base):
    """
       Column   |            Type             |                          Modifiers
    ------------+-----------------------------+-------------------------------------------------------------
     filesetid  | integer                     | not null default nextval('fileset_filesetid_seq'::regclass)
     fileset    | text                        | not null
     md5        | text                        | not null
     createtime | timestamp without time zone | not null

    Indexes:
        "fileset_pkey" PRIMARY KEY, btree (filesetid)
        "fileset_name_idx" btree (fileset)
    """
    createtime = Column('createtime', BaculaDateTime())


class Filename(ModelMixin, Base):
    """
       Column   |  Type   |                           Modifiers
    ------------+---------+---------------------------------------------------------------
     filenameid | integer | not null default nextval('filename_filenameid_seq'::regclass)
     name       | text    | not null

    Indexes:
        "filename_pkey" PRIMARY KEY, btree (filenameid)
        "filename_name_idx" btree (name)
    """


class Path(ModelMixin, Base):
    """
     Column |  Type   |                       Modifiers
    --------+---------+-------------------------------------------------------
     pathid | integer | not null default nextval('path_pathid_seq'::regclass)
     path   | text    | not null

    Indexes:
        "path_pkey" PRIMARY KEY, btree (pathid)
        "path_name_idx" btree (path)
    """


class File(ModelMixin, Base):
    """
       Column   |  Type   |                       Modifiers
    ------------+---------+-------------------------------------------------------
     fileid     | bigint  | not null default nextval('file_fileid_seq'::regclass)
     fileindex  | integer | not null default 0
     jobid      | integer | not null
     pathid     | integer | not null
     filenameid | integer | not null
     markid     | integer | not null default 0
     lstat      | text    | not null
     md5        | text    | not null

    Indexes:
        "file_pkey" PRIMARY KEY, btree (fileid)
        "file_jobid_idx" btree (jobid)
        "file_jpfid_idx" btree (jobid, pathid, filenameid)
    """

    filename = relationship(
        "Filename",
        lazy="joined",
        primaryjoin="File.filenameid==Filename.filenameid",
        foreign_keys="File.filenameid",
        innerjoin=True,
    )
    path = relationship(
        "Path",
        lazy="joined",
        primaryjoin="File.pathid==Path.pathid",
        foreign_keys="File.pathid",
        innerjoin=True,
    )

    # lstat: http://docs.python.org/library/os.html?highlight=lstat#os.stat
    # dev    ino      mode   nlink  uid gid rdev bytes  blksize blocks atime       mtime       ctime       optional
    # [2049, 6160392, 16877, 2,     0,  0,  0,   16384, 4096,   32,    1304426698, 1330102044, 1330102044, 0, 0, 2]

    def get_stat_data(self):
        data = getattr(self, 'lstat_raw', None)
        if data is None:
            self.lstat_raw = [decode_base64(s) for s in self.lstat.split()]
            return self.lstat_raw
        else:
            return data

    def render_size(self, request):
        return {'text': self.format_byte_size(self.get_stat_data()[7])}

    def render_uid(self, request):
        return {'text': self.get_stat_data()[4]}

    def render_gid(self, request):
        return {'text': self.get_stat_data()[5]}

    def render_mode(self, request):
        return {'text': oct(stat.S_IMODE(self.get_stat_data()[2]))}

    # TODO: pathvisibility: size and number of files in directory
    # TODO: pathhierarchy: parent-child relationship with paths
