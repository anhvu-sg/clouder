# -*- coding: utf-8 -*-
##############################################################################
#
#    Author: Yannick Buron
#    Copyright 2013 Yannick Buron
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################

from openerp import modules
from openerp import models, fields, api, _
from openerp.exceptions import except_orm

from datetime import datetime, timedelta
import execute

import logging
_logger = logging.getLogger(__name__)


class ClouderDomain(models.Model):
    _name = 'clouder.domain'
    _inherit = ['clouder.model']

    name = fields.Char('Domain name', size=64, required=True)
    organisation = fields.Char('Organisation', size=64, required=True)
    dns_server_id = fields.Many2one('clouder.container', 'DNS Server', required=True)
    cert_key = fields.Text('Wildcard Cert Key')
    cert_cert = fields.Text('Wildcart Cert')

    _sql_constraints = [
        ('name_uniq', 'unique(name)', 'Name must be unique!'),
    ]

    @api.multi
    def get_vals(self):

        vals = {}

        vals.update(self.env.ref('clouder.clouder_settings').get_vals())

        dns_vals = self.dns_server_id.get_vals()

        vals.update({
            'dns_id': dns_vals['container_id'],
            'dns_name': dns_vals['container_name'],
            'dns_fullname': dns_vals['container_fullname'],
            'dns_ssh_port': dns_vals['container_ssh_port'],
            'dns_server_id': dns_vals['server_id'],
            'dns_server_domain': dns_vals['server_domain'],
            'dns_server_ip': dns_vals['server_ip'],
        })

        vals.update({
            'domain_name': self.name,
            'domain_organisation': self.organisation,
            'domain_configfile': '/etc/bind/db.' + self.name,
            'domain_certkey': self.cert_key,
            'domain_certcert': self.cert_cert,
        })

        return vals



    def deploy(self, cr, uid, vals, context={}):
        context.update({'clouder-self': self, 'clouder-cr': cr, 'clouder-uid': uid})
        ssh, sftp = execute.connect(vals['dns_fullname'], username='root', context=context)
        sftp.put(modules.get_module_path('clouder') + '/res/bind.config', vals['domain_configfile'])
        execute.execute(ssh, ['sed', '-i', '"s/DOMAIN/' + vals['domain_name'] + '/g"', vals['domain_configfile']], context)
        execute.execute(ssh, ['sed', '-i', '"s/IP/' + vals['dns_server_ip'] + '/g"', vals['domain_configfile']], context)
        execute.execute(ssh, ["echo 'zone \"" + vals['domain_name'] + "\" {' >> /etc/bind/named.conf"], context)
        execute.execute(ssh, ['echo "type master;" >> /etc/bind/named.conf'], context)
        execute.execute(ssh, ['echo "allow-transfer {213.186.33.199;};" >> /etc/bind/named.conf'], context)
        execute.execute(ssh, ["echo 'file \"/etc/bind/db." + vals['domain_name'] + "\";' >> /etc/bind/named.conf"], context)
        execute.execute(ssh, ['echo "notify yes;" >> /etc/bind/named.conf'], context)
        execute.execute(ssh, ['echo "};" >> /etc/bind/named.conf'], context)
        execute.execute(ssh, ['echo "//END ' + vals['domain_name'] + '" >> /etc/bind/named.conf'], context)
        execute.execute(ssh, ['/etc/init.d/bind9', 'reload'], context)
        ssh.close()
        sftp.close()

    def purge(self, cr, uid, vals, context={}):
        context.update({'clouder-self': self, 'clouder-cr': cr, 'clouder-uid': uid})
        ssh, sftp = execute.connect(vals['dns_fullname'], username='root', context=context)
        execute.execute(ssh, ['sed', '-i', "'/zone\s\"" + vals['domain_name'] + "\"/,/END\s" + vals['domain_name'] + "/d'", '/etc/bind/named.conf'], context)
        execute.execute(ssh, ['rm', vals['domain_configfile']], context)
        execute.execute(ssh, ['/etc/init.d/bind9', 'reload'], context)
        ssh.close()
        sftp.close()

class ClouderBase(models.Model):
    _name = 'clouder.base'
    _inherit = ['clouder.model']

    name = fields.Char('Name', size=64, required=True)
    title = fields.Char('Title', size=64, required=True)
    application_id = fields.Many2one('clouder.application', 'Application', required=True)
    domain_id = fields.Many2one('clouder.domain', 'Domain name', required=True)
    service_id = fields.Many2one('clouder.service', 'Service', required=True)
    service_ids = fields.Many2many('clouder.service', 'clouder_base_service_rel', 'base_id', 'service_id', 'Alternative Services')
    admin_name = fields.Char('Admin name', size=64, required=True)
    admin_passwd = fields.Char('Admin password', size=64, required=True)
    admin_email = fields.Char('Admin email', size=64, required=True)
    poweruser_name = fields.Char('PowerUser name', size=64)
    poweruser_passwd = fields.Char('PowerUser password', size=64)
    poweruser_email = fields.Char('PowerUser email', size=64)
    build = fields.Selection([
                 ('none','No action'),
                 ('build','Build'),
                 ('restore','Restore')],'Build?')
    ssl_only = fields.Boolean('SSL Only?')
    test = fields.Boolean('Test?')
    lang = fields.Selection([('en_US','en_US'),('fr_FR','fr_FR')], 'Language', required=True)
    state = fields.Selection([
                ('installing','Installing'),
                ('enabled','Enabled'),
                ('blocked','Blocked'),
                ('removing','Removing')],'State',readonly=True)
    option_ids = fields.One2many('clouder.base.option', 'base_id', 'Options')
    link_ids = fields.One2many('clouder.base.link', 'base_id', 'Links')
    save_repository_id = fields.Many2one('clouder.save.repository', 'Save repository')
    time_between_save = fields.Integer('Minutes between each save')
    saverepo_change = fields.Integer('Days before saverepo change')
    saverepo_expiration = fields.Integer('Days before saverepo expiration')
    save_expiration = fields.Integer('Days before save expiration')
    date_next_save = fields.Datetime('Next save planned')
    save_comment = fields.Text('Save Comment')
    nosave = fields.Boolean('No save?')
    reset_each_day = fields.Boolean('Reset each day?')
    cert_key = fields.Text('Cert Key')
    cert_cert = fields.Text('Cert')
    parent_id = fields.Many2one('clouder.base','Parent Base')
    backup_server_ids = fields.Many2many('clouder.container', 'clouder_base_backup_rel', 'base_id', 'backup_id', 'Backup containers', required=True)

    _defaults = {
      'build': 'restore',
      'admin_passwd': execute.generate_random_password(20),
      'poweruser_passwd': execute.generate_random_password(12),
      'lang': 'en_US'
    }

    _sql_constraints = [
        ('name_uniq', 'unique (name,domain_id)', 'Name must be unique per domain !')
    ]

    def _check_application(self, cr, uid, ids, context=None):
        for b in self.browse(cr, uid, ids, context=context):
            if b.application_id.id != b.service_id.application_id.id:
                return False
            for s in b.service_ids:
                if b.application_id.id != s.application_id.id:
                    return False
        return True

    _constraints = [
        (_check_application, "The application of base must be the same than the application of service." , ['service_id','service_ids']),
    ]


#########TODO La liaison entre base et service est un many2many � cause du loadbalancing. Si le many2many est vide, un service est cr�� automatiquement. Finalement il y aura un many2one pour le principal, et un many2many pour g�rer le loadbalancing
#########Contrainte : L'application entre base et service doit �tre la m�me, de plus la bdd/host/db_user/db_password doit �tre la m�me entre tous les services d'une m�me base

    @api.multi
    def get_vals(self):
        repo_obj = self.pool.get('clouder.save.repository')
        vals = {}

        now = datetime.now()
        if not self.save_repository_id:
            repo_ids = repo_obj.search([('base_name','=',self.name),('base_domain','=',self.domain_id.name)])
            if repo_ids:
                self.write({'save_repository_id': repo_ids[0]})

        if not self.save_repository_id or datetime.strptime(self.save_repository_id.date_change, "%Y-%m-%d") < now or False:
            repo_vals ={
                'name': now.strftime("%Y-%m-%d") + '_' + self.name + '_' + self.domain_id.name,
                'type': 'base',
                'date_change': (now + timedelta(days=self.saverepo_change or self.application_id.base_saverepo_change)).strftime("%Y-%m-%d"),
                'date_expiration': (now + timedelta(days=self.saverepo_expiration or self.application_id.base_saverepo_expiration)).strftime("%Y-%m-%d"),
                'base_name': self.name,
                'base_domain': self.domain_id.name,
            }
            repo_id = repo_obj.create(repo_vals)
            self.write({'save_repository_id': repo_id})


        vals.update(self.domain_id.get_vals())
        vals.update(self.service_id.get_vals())
        vals.update(self.save_repository_id.get_vals())

        unique_name = vals['app_code'] + '-' + self.name + '-' + self.domain_id.name
        unique_name = unique_name.replace('.','-')

        options = {}
        for option in self.service_id.container_id.application_id.type_id.option_ids:
            if option.type == 'base':
                options[option.name] = {'id': option.id, 'name': option.name, 'value': option.default}
        for option in self.option_ids:
            options[option.name.name] = {'id': option.id, 'name': option.name.name, 'value': option.value}

        links = {}
        if 'app_links' in vals:
            for app_code, link in vals['app_links'].iteritems():
                if link['base']:
                    links[app_code] = link
                    links[app_code]['target'] = False
        for link in self.link_ids:
            if link.name.code in links and link.target:
                link_vals = link.target.get_vals()
                links[link.name.code]['target'] = {
                    'link_id': link_vals['container_id'],
                    'link_name': link_vals['container_name'],
                    'link_fullname': link_vals['container_fullname'],
                    'link_ssh_port': link_vals['container_ssh_port'],
                    'link_server_id': link_vals['server_id'],
                    'link_server_domain': link_vals['server_domain'],
                    'link_server_ip': link_vals['server_ip'],
                }
        links_temp = links
        for app_code, link in links.iteritems():
            if link['required'] and not link['target']:
                raise except_orm(_('Data error!'),
                    _("You need to specify a link to " + link['name'] + " for the base " + self.name))
            # if not link['target']:
            #     del links_temp[app_code]
        links = links_temp

        backup_servers = []
        for backup in self.backup_server_ids:
            backup_vals = backup.get_vals()
            backup_servers.append({
                'container_id': backup_vals['container_id'],
                'container_fullname': backup_vals['container_fullname'],
                'server_id': backup_vals['server_id'],
                'server_ssh_port': backup_vals['server_ssh_port'],
                'server_domain': backup_vals['server_domain'],
                'server_ip': backup_vals['server_ip'],
                'backup_method': backup_vals['app_options']['backup_method']['value']
            })

        unique_name_ = unique_name.replace('-','_')
        databases = {'single': unique_name_}
        databases_comma = ''
        if vals['apptype_multiple_databases']:
            databases = {}
            first = True
            for database in vals['apptype_multiple_databases'].split(','):
                if not first:
                    databases_comma += ','
                databases[database] = unique_name_ + '_' + database
                databases_comma += databases[database]
                first = False
        vals.update({
            'base_id': self.id,
            'base_name': self.name,
            'base_fullname': unique_name,
            'base_fulldomain': self.name + '.' + self.domain_id.name,
            'base_unique_name': unique_name,
            'base_unique_name_': unique_name_,
            'base_title': self.title,
            'base_domain': self.domain_id.name,
            'base_admin_name': self.admin_name,
            'base_admin_passwd': self.admin_passwd,
            'base_admin_email': self.admin_email,
            'base_poweruser_name': self.poweruser_name,
            'base_poweruser_password': self.poweruser_passwd,
            'base_poweruser_email': self.poweruser_email,
            'base_build': self.build,
            'base_sslonly': self.ssl_only,
            'base_certkey': self.cert_key,
            'base_certcert': self.cert_cert,
            'base_test': self.test,
            'base_lang': self.lang,
            'base_nosave': self.nosave,
            'base_options': options,
            'base_links': links,
            'base_nginx_configfile': '/etc/nginx/sites-available/' + unique_name,
            'base_shinken_configfile': '/usr/local/shinken/etc/services/' + unique_name + '.cfg',
            'base_databases': databases,
            'base_databases_comma': databases_comma,
            'base_backup_servers': backup_servers
        })

        return vals

    def create(self, cr, uid, vals, context={}):
        if (not 'service_id' in vals) or (not vals['service_id']):
            application_obj = self.pool.get('clouder.application')
            domain_obj = self.pool.get('clouder.domain')
            container_obj = self.pool.get('clouder.container')
            service_obj = self.pool.get('clouder.service')
            if 'application_id' not in vals or not vals['application_id']:
                raise except_orm(_('Error!'),_("You need to specify the application of the base."))
            application = application_obj.browse(cr, uid, vals['application_id'], context=context)
            if not application.next_server_id:
                raise except_orm(_('Error!'),_("You need to specify the next server in application for the container autocreate."))
            if not application.default_image_id.version_ids:
                raise except_orm(_('Error!'),_("No version for the image linked to the application, abandoning container autocreate..."))
            if not application.version_ids:
                raise except_orm(_('Error!'),_("No version for the application, abandoning service autocreate..."))
            if 'domain_id' not in vals or not vals['domain_id']:
                raise except_orm(_('Error!'),_("You need to specify the domain of the base."))
            domain = domain_obj.browse(cr, uid, vals['domain_id'], context=context)
            container_vals = {
                'name': vals['name'] + '_' + domain.name.replace('.','_').replace('-','_'),
                'server_id': application.next_server_id.id,
                'application_id': application.id,
                'image_id': application.default_image_id.id,
                'image_version_id': application.default_image_id.version_ids[0].id,
            }
            container_id = container_obj.create(cr, uid, container_vals, context=context)
            service_vals = {
                'name': 'production',
                'container_id': container_id,
                'application_version_id': application.version_ids[0].id,
            }
            vals['service_id'] = service_obj.create(cr, uid, service_vals, context=context)
        if 'application_id' in vals:
            config = self.pool.get('ir.model.data').get_object(cr, uid, 'clouder', 'clouder_settings')
            application = self.pool.get('clouder.application').browse(cr, uid, vals['application_id'], context=context)
            if 'admin_name' not in vals or not vals['admin_name']:
                vals['admin_name'] = application.admin_name
            if 'admin_email' not in vals or not vals['admin_email']:
                vals['admin_email'] = application.admin_email and application.admin_email or config.sysadmin_email
            if 'backup_server_ids' not in vals or not vals['backup_server_ids'] or not vals['backup_server_ids'][0][2]:
                vals['backup_server_ids'] = [(6,0,[b.id for b in application.base_backup_ids])]
            if 'time_between_save' not in vals or not vals['time_between_save']:
                vals['time_between_save'] = application.base_time_between_save
            if 'saverepo_change' not in vals or not vals['saverepo_change']:
                vals['saverepo_change'] = application.base_saverepo_change
            if 'saverepo_expiration' not in vals or not vals['saverepo_expiration']:
                vals['saverepo_expiration'] = application.base_saverepo_expiration
            if 'save_expiration' not in vals or not vals['save_expiration']:
                vals['save_expiration'] = application.base_save_expiration

            links = {}
            for link in application.link_ids:
                if link.base:
                    links[link.name.id] = {}
                    links[link.name.id]['required'] = link.required
                    links[link.name.id]['name'] = link.name.name
                    links[link.name.id]['target'] = link.auto and link.next and link.next.id or False
            if 'link_ids' in vals:
                for link in vals['link_ids']:
                    link = link[2]
                    if link['name'] in links:
                        links[link['name']]['target'] = link['target']
                del vals['link_ids']
            vals['link_ids'] = []
            for application_id, link in links.iteritems():
                if link['required'] and not link['target']:
                    raise except_orm(_('Data error!'),
                        _("You need to specify a link to " + link['name'] + " for the base " + vals['name']))
                vals['link_ids'].append((0,0,{'name': application_id, 'target': link['target']}))
        return super(ClouderBase, self).create(cr, uid, vals, context=context)

    def write(self, cr, uid, ids, vals, context={}):
        save_obj = self.pool.get('clouder.save.save')
        if 'service_id' in vals:
            for base in self.browse(cr, uid, ids, context=context):
                context = self.create_log(cr, uid, base.id, 'service change', context)
                context['save_comment'] = 'Before service change'
                context['forcesave'] = True
                save_id = self.save(cr, uid, [base.id], context=context)[base.id]
                del context['forcesave']
                base_vals = self.get_vals(cr, uid, base.id, context=context)
                self.purge(cr, uid, base_vals, context=context)
                break
        res = super(ClouderBase, self).write(cr, uid, ids, vals, context=context)
        if 'service_id' in vals:
            for base in self.browse(cr, uid, ids, context=context):
                save_obj.write(cr, uid, [save_id], {'service_id': vals['service_id']}, context=context)
                context['base_restoration'] = True
                base_vals = self.get_vals(cr, uid, base.id, context=context)
                self.deploy(cr, uid, base_vals, context=context)
                save_obj.restore(cr, uid, [save_id], context=context)
                self.end_log(cr, uid, base.id, context=context)
                break
        if 'nosave' in vals or 'ssl_only' in vals:
            self.deploy_links(cr, uid, ids, context=context)

        return res

    def unlink(self, cr, uid, ids, context={}):
        context['save_comment'] = 'Before unlink'
        self.save(cr, uid, ids, context=context)
        return super(ClouderBase, self).unlink(cr, uid, ids, context=context)

    def save(self, cr, uid, ids, context={}):
        context.update({'clouder-self': self, 'clouder-cr': cr, 'clouder-uid': uid})
        save_obj = self.pool.get('clouder.save.save')

        res = {}
        now = datetime.now()
        for base in self.browse(cr, uid, ids, context=context):
            if 'nosave' in context or (base.nosave and not 'forcesave' in context):
                execute.log('This base shall not be saved or the backup isnt configured in conf, skipping save base', context)
                continue
            context = self.create_log(cr, uid, base.id, 'save', context)
            vals = self.get_vals(cr, uid, base.id, context=context)
            for backup_server in vals['base_backup_servers']:
                if not 'backup_server_domain' in vals:
                    execute.log('The backup isnt configured in conf, skipping save base', context)
                    return
                    return
                container_links = {}
                for app_code, link in vals['container_links'].iteritems():
                    container_links[app_code] = {
                        'name': link['app_id'],
                        'name_name': link['name'],
                        'target': link['target'] and link['target']['link_id'] or False
                    }
                service_links = {}
                for app_code, link in vals['service_links'].iteritems():
                    service_links[app_code] = {
                        'name': link['app_id'],
                        'name_name': link['name'],
                        'target': link['target'] and link['target']['link_id'] or False
                    }
                base_links = {}
                for app_code, link in vals['base_links'].iteritems():
                    base_links[app_code] = {
                        'name': link['app_id'],
                        'name_name': link['name'],
                        'target': link['target'] and link['target']['link_id'] or False
                    }
                save_vals = {
                    'name': vals['now_bup'] + '_' + vals['base_unique_name'],
                    'backup_server_id': backup_server['container_id'],
                    'repo_id': vals['saverepo_id'],
                    'date_expiration': (now + timedelta(days=base.save_expiration or base.application_id.base_save_expiration)).strftime("%Y-%m-%d"),
                    'comment': 'save_comment' in context and context['save_comment'] or base.save_comment or 'Manual',
                    'now_bup': vals['now_bup'],
                    'container_id': vals['container_id'],
                    'container_volumes_comma': vals['container_volumes_save'],
                    'container_app': vals['app_code'],
                    'container_img': vals['image_name'],
                    'container_img_version': vals['image_version_name'],
                    'container_ports': str(vals['container_ports']),
                    'container_volumes': str(vals['container_volumes']),
                    'container_options': str(vals['container_options']),
                    'container_links': str(container_links),
                    'service_id': vals['service_id'],
                    'service_name': vals['service_name'],
                    'service_database_id': vals['database_id'],
                    'service_options': str(vals['service_options']),
                    'service_links': str(service_links),
                    'base_id': vals['base_id'],
                    'base_title': vals['base_title'],
                    'base_app_version': vals['app_version_name'],
                    'base_proxy_id': 'proxy_id' in vals and vals['proxy_id'],
                    'base_mail_id': 'mail_id' in vals and vals['mail_id'],
                    'base_container_name': vals['container_name'],
                    'base_container_server': vals['server_domain'],
                    'base_admin_passwd': vals['base_admin_passwd'],
                    'base_poweruser_name': vals['base_poweruser_name'],
                    'base_poweruser_password': vals['base_poweruser_password'],
                    'base_poweruser_email': vals['base_poweruser_email'],
                    'base_build': vals['base_build'],
                    'base_test': vals['base_test'],
                    'base_lang': vals['base_lang'],
                    'base_nosave': vals['base_nosave'],
                    'base_options': str(vals['base_options']),
                    'base_links': str(base_links),
                }
                res[base.id] = save_obj.create(cr, uid, save_vals, context=context)
            next = (datetime.now() + timedelta(minutes=base.time_between_save or base.application_id.base_time_between_save)).strftime("%Y-%m-%d %H:%M:%S")
            self.write(cr, uid, [base.id], {'save_comment': False, 'date_next_save': next}, context=context)
            self.end_log(cr, uid, base.id, context=context)
        return res

    def reset_base(self, cr, uid, ids, context={}):
        self._reset_base(cr, uid,ids, context=context)

    def post_reset(self, cr, uid, vals, context=None):
        self.deploy_links(cr, uid, [vals['base_id']], context=context)
        return

    def _reset_base(self, cr, uid, ids, base_name=False, service_id=False, context={}):
        save_obj = self.pool.get('clouder.save.save')
        for base in self.browse(cr, uid, ids, context=context):
            base_parent_id = base.parent_id and base.parent_id.id or base.id
            vals_parent = self.get_vals(cr, uid, base_parent_id, context=context)
            if not 'save_comment' in context:
                context['save_comment'] = 'Reset base'
            context['forcesave'] = True
            save_id = self.save(cr, uid, [base_parent_id], context=context)[base_parent_id]
            del context['forcesave']
            context['nosave'] = True
            vals = {'base_id': base.id, 'base_restore_to_name': base.name, 'base_restore_to_domain_id': base.domain_id.id, 'service_id': base.service_id.id, 'base_nosave': True}
            if base_name:
                vals = {'base_id': False, 'base_restore_to_name': base_name, 'base_restore_to_domain_id': base.domain_id.id, 'service_id': service_id, 'base_nosave': True}
            save_obj.write(cr, uid, [save_id], vals)
            base_id = save_obj.restore(cr, uid, [save_id], context=context)
            self.write(cr, uid, [base_id], {'parent_id': base_parent_id}, context=context)
            vals = self.get_vals(cr, uid, base_id, context=context)
            vals['base_parent_unique_name_'] = vals_parent['base_unique_name_']
            vals['service_parent_name'] = vals_parent['service_name']
            self.update_base(cr, uid, vals, context=context)
            self.post_reset(cr, uid, vals, context=context)
            self.deploy_post(cr, uid, vals, context=context)


    def deploy_create_database(self, cr, uid, vals, context=None):
        return False

    def deploy_build(self, cr, uid, vals, context=None):
        return

    def deploy_post_restore(self, cr, uid, vals, context=None):
        return

    def deploy_create_poweruser(self, cr, uid, vals, context=None):
        return

    def deploy_test(self, cr, uid, vals, context=None):
        return

    def deploy_post(self, cr, uid, vals, context=None):
        return

    def deploy_prepare_apache(self, cr, uid, vals, context=None):
        return

    def deploy(self, cr, uid, vals, context=None):
        context.update({'clouder-self': self, 'clouder-cr': cr, 'clouder-uid': uid})
        self.purge(cr, uid, vals, context=context)

        if 'base_restoration' in context:
            return

        res = self.deploy_create_database(cr, uid, vals, context)
        if not res:
            for key, database in vals['base_databases'].iteritems():
                if vals['database_type'] != 'mysql':
                    ssh, sftp = execute.connect(vals['container_fullname'], username=vals['apptype_system_user'], context=context)
                    execute.execute(ssh, ['createdb', '-h', vals['database_server'], '-U', vals['service_db_user'], database], context)
                    ssh.close()
                    sftp.close()
                else:
                    ssh, sftp = execute.connect(vals['database_fullname'], context=context)
                    execute.execute(ssh, ["mysql -u root -p'" + vals['database_root_password'] + "' -se \"create database " + database + ";\""], context)
                    execute.execute(ssh, ["mysql -u root -p'" + vals['database_root_password'] + "' -se \"grant all on " + database + ".* to '" + vals['service_db_user'] + "';\""], context)
                    ssh.close()
                    sftp.close()

        execute.log('Database created', context)
        if vals['base_build'] == 'build':
            self.deploy_build(cr, uid, vals, context)

        elif vals['base_build'] == 'restore':
            if vals['database_type'] != 'mysql':
                ssh, sftp = execute.connect(vals['container_fullname'], username=vals['apptype_system_user'], context=context)
                execute.execute(ssh, ['pg_restore', '-h', vals['bdd_server_domain'], '-U', vals['service_db_user'], '--no-owner', '-Fc', '-d', vals['base_unique_name_'], vals['app_version_full_localpath'] + '/' + vals['app_bdd'] + '/build.sql'], context)
                ssh.close()
                sftp.close()
            else:
                ssh, sftp = execute.connect(vals['container_fullname'], username=vals['apptype_system_user'], context=context)
                execute.execute(ssh, ['mysql', '-h', vals['bdd_server_domain'], '-u', vals['service_db_user'], '-p' + vals['bdd_server_mysql_passwd'], vals['base_unique_name_'], '<', vals['app_version_full_localpath'] + '/' + vals['app_bdd'] + '/build.sql'], context)
                ssh.close()
                sftp.close()

            self.deploy_post_restore(cr, uid, vals, context)

        if vals['base_build'] != 'none':
            if vals['base_poweruser_name'] and vals['base_poweruser_email'] and vals['apptype_admin_name'] != vals['base_poweruser_name']:
                self.deploy_create_poweruser(cr, uid, vals, context)
            if vals['base_test']:
                self.deploy_test(cr, uid, vals, context)


        self.deploy_post(cr, uid, vals, context)

        #For shinken
        self.save(cr, uid, [vals['base_id']], context=context)



    def purge_post(self, cr, uid, vals, context=None):
        return

    def purge_db(self, cr, uid, vals, context=None):
        context.update({'clouder-self': self, 'clouder-cr': cr, 'clouder-uid': uid})
        for key, database in vals['base_databases'].iteritems():
            if vals['database_type'] != 'mysql':
                ssh, sftp = execute.connect(vals['database_fullname'], username='postgres', context=context)
                execute.execute(ssh, ['psql', '-c', '"update pg_database set datallowconn = \'false\' where datname = \'' + database + '\'; SELECT pg_terminate_backend(procpid) FROM pg_stat_activity WHERE datname = \'' + database + '\';"'], context)
                execute.execute(ssh, ['dropdb', database], context)
                ssh.close()
                sftp.close()

            else:
                ssh, sftp = execute.connect(vals['database_fullname'], context=context)
                execute.execute(ssh, ["mysql -u root -p'" + vals['database_root_password'] + "' -se \"drop database " + database + ";\""], context)
                ssh.close()
                sftp.close()
        return

    def purge(self, cr, uid, vals, context={}):
        context.update({'clouder-self': self, 'clouder-cr': cr, 'clouder-uid': uid})

        self.purge_db(cr, uid, vals, context=context)

        self.purge_post(cr, uid, vals, context)

    def update_base(self, cr, uid, vals, context=None):
        return



class ClouderBaseOption(models.Model):
    _name = 'clouder.base.option'

    base_id = fields.Many2one('clouder.base', 'Base', ondelete="cascade", required=True)
    name = fields.Many2one('clouder.application.type.option', 'Option', required=True)
    value = fields.Text('Value')

    _sql_constraints = [
        ('name_uniq', 'unique(base_id,name)', 'Option name must be unique per base!'),
    ]


class ClouderBaseLink(models.Model):
    _name = 'clouder.base.link'

    base_id = fields.Many2one('clouder.base', 'Base', ondelete="cascade", required=True)
    name = fields.Many2one('clouder.application', 'Application', required=True)
    target = fields.Many2one('clouder.container', 'Target')


    _sql_constraints = [
        ('name_uniq', 'unique(base_id,name)', 'Links must be unique per base!'),
    ]


    @api.multi
    def get_vals(self):
        vals = {}

        vals.update(self.base_id.get_vals())
        if self.target:
            target_vals = self.target_id.get_vals()
            vals.update({
                'link_target_container_id': target_vals['container_id'],
                'link_target_container_name': target_vals['container_name'],
                'link_target_container_fullname': target_vals['container_fullname'],
                'link_target_app_id': target_vals['app_id'],
                'link_target_app_code': target_vals['app_code'],
            })
            service_ids = self.env['clouder.service'].search([('container_id', '=', self.target.id)])
            base_ids = self.env['clouder.base'].search([('service_id', 'in', service_ids)])
            if base_ids:
                base_vals = base_ids[0].get_vals()
                vals.update({
                    'link_target_service_db_user': base_vals['service_db_user'],
                    'link_target_service_db_password': base_vals['service_db_password'],
                    'link_target_database_server': base_vals['database_server'],
                    'link_target_base_unique_name_': base_vals['base_unique_name_'],
                    'link_target_base_fulldomain': base_vals['base_fulldomain'],
                })


        return vals

    def reload(self, cr, uid, ids, context=None):
        for link_id in ids:
            vals = self.get_vals(cr, uid, link_id, context=context)
            self.deploy(cr, uid, vals, context=context)
        return

    def deploy_link(self, cr, uid, vals, context={}):
        return

    def deploy(self, cr, uid, vals, context={}):
        context.update({'clouder-self': self, 'clouder-cr': cr, 'clouder-uid': uid})
        self.purge(cr, uid, vals, context=context)
        if not 'link_target_container_id' in vals:
            execute.log('The target isnt configured in the link, skipping deploy link', context)
            return
        if vals['link_target_app_code'] not in vals['base_links']:
            execute.log('The target isnt in the application link for base, skipping deploy link', context)
            return
        if not vals['base_links'][vals['link_target_app_code']]['base']:
            execute.log('This application isnt for base, skipping deploy link', context)
            return
        self.deploy_link(cr, uid, vals, context=context)

    def purge_link(self, cr, uid, vals, context={}):
        return

    def purge(self, cr, uid, vals, context={}):
        context.update({'clouder-self': self, 'clouder-cr': cr, 'clouder-uid': uid})
        if not 'link_target_container_id' in vals:
            execute.log('The target isnt configured in the link, skipping deploy link', context)
            return
        if vals['link_target_app_code'] not in vals['base_links']:
            execute.log('The target isnt in the application link for base, skipping deploy link', context)
            return
        if not vals['base_links'][vals['link_target_app_code']]['base']:
            execute.log('This application isnt for base, skipping deploy link', context)
            return
        self.purge_link(cr, uid, vals, context=context)