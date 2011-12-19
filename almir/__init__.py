from pyramid.config import Configurator
from pyramid.events import BeforeRender
from pyramid.httpexceptions import HTTPNotFound
from pyramid.view import append_slash_notfound_view
from sqlalchemy import engine_from_config

from almir.meta import initialize_sql
from almir.lib.filters import filters


# TODO: cache
def navigation_tree(event):
    """Generate navigation data"""
    request = event['request']
    event['navigation_tree'] = [
        dict(name="Dashboard", url=request.route_url('dashboard')),
        dict(name="Clients", url=request.route_url('client_list')),
        # TODO: does this make sense? dict(name="FileSets", url=request.route_url('fileset_list')),
        dict(name="Storages", url=request.route_url('storage_list')),
        dict(name="Jobs", url=request.route_url('job_list')),
        dict(name="Volumes", url=request.route_url('volume_list')),
        dict(name="Pools", url=request.route_url('pool_list')),
        dict(name="Logs", url=request.route_url('log')),
        dict(name="Console", url=request.route_url('console')),
    ]
    for i, item in enumerate(event['navigation_tree']):
        try:
            event['navigation_tree'][i]['active_class'] = request.current_route_url() == item['url'] and "active" or ""
        except ValueError:
            # Current request matches no route
            break


def main(global_config, **settings):
    """ This function returns a Pyramid WSGI application. """
    engine = engine_from_config(settings, prefix='sqlalchemy.', client_encoding='utf8')
    initialize_sql(engine)
    config = Configurator(settings=settings)

    # events
    config.add_subscriber(filters, BeforeRender)
    config.add_subscriber(navigation_tree, BeforeRender)

    # static
    config.add_static_view('static', 'almir:static', cache_max_age=3600)
    config.add_static_view('static_deform', 'deform:static')

    # routes
    config.add_route('dashboard', '/')
    config.add_view('almir.views.dashboard',
                    route_name='dashboard',
                    renderer='templates/dashboard.pt')
    config.add_route('about', '/about')
    config.add_view('almir.views.about',
                    route_name='about',
                    renderer='templates/about.pt')
    config.add_route('log', '/log')
    config.add_view('almir.views.log',
                    route_name='log',
                    renderer='templates/log.pt')
    config.add_route('console', '/console')
    config.add_view('almir.views.console',
                    route_name='console',
                    renderer='templates/console.pt')
    config.add_route('console_ajax', '/console/ajax')
    config.add_view('almir.views.console_ajax',
                    route_name='console_ajax',
                    renderer='json',
                    request_method='POST')

    # RESTful resources
    for name in ['job', 'client', 'storage', 'volume', 'pool']:
        for action, url in [('list', '/%s' % name), ('detail', '/%s/{id:\d+}' % name)]:
            config.add_route('%s_%s' % (name, action), url)
            config.add_view(
                'almir.views.%sView' % name.title(),
                route_name='%s_%s' % (name, action),
                attr=action,
                renderer='templates/%s_%s.pt' % (name, action),
            )

    config.add_view(append_slash_notfound_view, context=HTTPNotFound)

    return config.make_wsgi_app()