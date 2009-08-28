from django.db import models, connection
from django.contrib.gis.db import models
from django.contrib.gis.maps.google import GoogleMap, GMarker, GEvent, GPolygon, GIcon
from django.template.loader import render_to_string
from fixmystreet import settings
from django import forms
from django.core.mail import send_mail, EmailMessage
import md5
import urllib
import time
from datetime import datetime as dt
from django.utils.safestring import mark_safe
from django.utils.translation import ugettext_lazy, ugettext as _
from contrib.transmeta import TransMeta
from contrib.stdimage import StdImageField
import libxml2
from django.utils.encoding import iri_to_uri
      
        
class Province(models.Model):
    name = models.CharField(max_length=100)
    abbrev = models.CharField(max_length=3)

    class Meta:
        db_table = u'province'
    
class City(models.Model):
    province = models.ForeignKey(Province)
    name = models.CharField(max_length=100)
    # the city's 311 email, if it has one.
    email = models.EmailField(blank=True, null=True)    
    # unused, for now.
    geom = models.PolygonField( null=True)

    objects = models.GeoManager()

    def __unicode__(self):      
        return self.name


    def get_absolute_url(self):
        return settings.SITE_URL + "/cities/" + str(self.id)

    class Meta:
        db_table = u'cities'

class Councillor(models.Model):
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    
    # this email addr. is used to send reports to if there is no 311 email for the city.
    email = models.EmailField(blank=True, null=True)
    fax = models.CharField(max_length=20,blank=True, null=True)
    phone = models.CharField(max_length=20,blank=True, null=True)

    class Meta:
        db_table = u'councillors'
   
class Ward(models.Model):
    name = models.CharField(max_length=100)
    number = models.IntegerField()
    councillor = models.ForeignKey(Councillor)
    city = models.ForeignKey(City)
    geom = models.MultiPolygonField( null=True)
    objects = models.GeoManager()
    
    def get_absolute_url(self):
        return settings.SITE_URL + "/wards/" + str(self.id)

    class Meta:
        db_table = u'wards'

class ReportCategoryClass(models.Model):
    __metaclass__ = TransMeta

    name = models.CharField(max_length=100)

    def __unicode__(self):      
        return self.name

    class Meta:
        db_table = u'report_category_classes'
        translate = ('name', )
    
class ReportCategory(models.Model):
    __metaclass__ = TransMeta

    name = models.CharField(max_length=100)
    hint = models.TextField(blank=True, null=True)
    category_class = models.ForeignKey(ReportCategoryClass)
  
    class Meta:
        db_table = u'report_categories'
        translate = ('name', 'hint', )
               
class Report(models.Model):
    title = models.CharField(max_length=100, verbose_name = ugettext_lazy("Subject"))
    category = models.ForeignKey(ReportCategory,null=True)
    ward = models.ForeignKey(Ward,null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    # last time report was updated
    updated_at = models.DateTimeField(auto_now_add=True)
    
    # time report was marked as 'fixed'
    fixed_at = models.DateTimeField(null=True)
    is_fixed = models.BooleanField(default=False)
    is_hate = models.BooleanField(default=False)
    
    # last time report was sent to city
    sent_at = models.DateTimeField(null=True)
    
    # email where the report was sent
    email_sent_to = models.EmailField(null=True)
    
    # last time a reminder was sent to the person that filed the report.
    reminded_at = models.DateTimeField(auto_now_add=True)
    
    point = models.PointField(null=True)
    photo = StdImageField(upload_to="photos", blank=True, verbose_name =  ugettext_lazy("* Photo"), size=(400, 400), thumbnail_size=(133,100))
    desc = models.TextField(blank=True, null=True, verbose_name = ugettext_lazy("Details"))
    author = models.CharField(max_length=255,verbose_name = ugettext_lazy("Name"))

    # true if first update has been confirmed - redundant with
    # one in ReportUpdate, but makes aggregate SQL queries easier.
    
    is_confirmed = models.BooleanField(default=False)

    objects = models.GeoManager()
    
    def is_subscribed(self, email):
        if len( self.reportsubscriber_set.filter(email=email)) != 0:
            return( True )
        return( self.first_update().email == email )
    
    def sent_at_diff(self):
        if not self.sent_at:
            return( None )
        else:
            return(  self.sent_at - self.created_at )

    def first_update(self):
        return( ReportUpdate.objects.get(report=self,first_update=True))

    def get_absolute_url(self):
        return settings.SITE_URL + "/reports/" + str(self.id)
            
    class Meta:
        db_table = u'reports'

class ReportCount(object):        
    def __init__(self, interval):
        self.interval = interval
    
    def dict(self):
        return({ "recent_new": "count( case when age(clock_timestamp(), reports.created_at) < interval '%s' THEN 1 ELSE null end )" % self.interval,
          "recent_fixed": "count( case when age(clock_timestamp(), reports.fixed_at) < interval '%s' AND reports.is_fixed = True THEN 1 ELSE null end )" % self.interval,
          "recent_updated": "count( case when age(clock_timestamp(), reports.updated_at) < interval '%s' AND reports.is_fixed = False and reports.updated_at != reports.created_at THEN 1 ELSE null end )" % self.interval,
          "old_fixed": "count( case when age(clock_timestamp(), reports.fixed_at) > interval '%s' AND reports.is_fixed = True THEN 1 ELSE null end )" % self.interval,
          "old_unfixed": "count( case when age(clock_timestamp(), reports.fixed_at) > interval '%s' AND reports.is_fixed = False THEN 1 ELSE null end )" % self.interval } )  
 
class ReportUpdate(models.Model):   
    report = models.ForeignKey(Report)
    desc = models.TextField(blank=True, null=True, verbose_name = ugettext_lazy("Details"))
    created_at = models.DateTimeField(auto_now_add=True)
    is_confirmed = models.BooleanField(default=False)
    is_fixed = models.BooleanField(default=False)
    confirm_token = models.CharField(max_length=255, null=True)
    email = models.EmailField(max_length=255, verbose_name = ugettext_lazy("Email"))
    author = models.CharField(max_length=255,verbose_name = ugettext_lazy("Name"))
    phone = models.CharField(max_length=255, verbose_name = ugettext_lazy("Phone") )
    first_update = models.BooleanField(default=False)
    
    def send_emails(self):
        if self.first_update:
            self.notify_on_new()
        else:
            self.notify_on_update()
            
    def notify_on_new(self):
        # send to the city immediately.           
        subject = render_to_string("emails/send_report_to_city/subject.txt", {'update': self })
        message = render_to_string("emails/send_report_to_city/message.txt", { 'update': self })
        
        if self.report.ward.city.email:
            email_addr = self.report.ward.city.email
        else:
            email_addr = self.report.ward.councillor.email
        
        email_msg = EmailMessage(subject,message,settings.EMAIL_FROM_USER, 
                        [email_addr], headers = {'Reply-To': self.email })
        if self.report.photo:
            email_msg.attach_file( self.report.photo.file.name )
        
        email_msg.send()

        # update report to show time sent to city.
        self.report.sent_at=dt.now()
        self.report.email_sent_to = email_addr
        self.report.save()
        
    
    def notify_on_update(self):
        subject = render_to_string("emails/report_update/subject.txt", 
                    { 'update': self })
        
        # tell our subscribers there was an update.
        for subscriber in self.report.reportsubscriber_set.all():
            unsubscribe_url = settings.SITE_URL + "/reports/subscribers/unsubscribe/" + subscriber.confirm_token
            message = render_to_string("emails/report_update/message.txt", 
               { 'update': self, 'unsubscribe_url': unsubscribe_url })
            send_mail(subject, message, 
               settings.EMAIL_FROM_USER,[subscriber.email], fail_silently=False)

        # tell the original problem reporter there was an update
        message = render_to_string("emails/report_update/message.txt", 
                    { 'update': self })
        send_mail(subject, message, 
              settings.EMAIL_FROM_USER,
              [self.report.first_update().email],  fail_silently=False)

            
    def save(self):
        if not self.confirm_token or self.confirm_token == "":
            m = md5.new()
            m.update(self.email)
            m.update(str(time.time()))
            self.confirm_token = m.hexdigest()
            confirm_url = settings.SITE_URL + "/reports/updates/confirm/" + self.confirm_token
            message = render_to_string("emails/confirm/message.txt", 
                    { 'confirm_url': confirm_url, 'update': self })
            subject = render_to_string("emails/confirm/subject.txt", 
                    {  'update': self })
            send_mail(subject, message, 
                   settings.EMAIL_FROM_USER,[self.email], fail_silently=False)
            
        super(ReportUpdate, self).save()
    
    def title(self):
        if self.first_update :
            return self.report.title
        if self.is_fixed:
            return "Reported Fixed"
        return("Update")
        
    class Meta:
        db_table = u'report_updates'

class ReportSubscriber(models.Model):
    """ 
        Report Subscribers are notified when there's an update.
    """
    
    report = models.ForeignKey(Report)    
    confirm_token = models.CharField(max_length=255, null=True)
    is_confirmed = models.BooleanField(default=False)    
    email = models.EmailField()

    class Meta:
        db_table = u'report_subscribers'

    
    def save(self):
        if not self.confirm_token or self.confirm_token == "":
            m = md5.new()
            m.update(self.email)
            m.update(str(time.time()))
            self.confirm_token = m.hexdigest()
            confirm_url = settings.SITE_URL + "/reports/subscribers/confirm/" + self.confirm_token
            message = render_to_string("emails/subscribe/message.txt", 
                    { 'confirm_url': confirm_url, 'subscriber': self })
            send_mail('Subscribe to FixMyStreet.ca Report Updates', message, 
                   settings.EMAIL_FROM_USER,[self.email], fail_silently=False)
        super(ReportSubscriber, self).save()

 
class ReportMarker(GMarker):
    """
        A marker for an existing report.  Override the GMarker class to 
        add a numbered, coloured marker.
        
        If the report is fixed, show a green marker, otherwise red.
    """
    def __init__(self, report, icon_number ):
        if report.is_fixed:
            color = 'green'
        else:
            color = 'red'
        icon_number = icon_number
        img = "/media/images/marker/%s/marker%s.png" %( color, icon_number )
        name = 'letteredIcon%s' %( icon_number )      
        icon = GIcon(name,image=img,iconsize=(20,34))
        GMarker.__init__(self,geom=(report.point.x,report.point.y), title=report.title, icon=icon)

    def __unicode__(self):
        "The string representation is the JavaScript API call."
        return mark_safe('GMarker(%s)' % ( self.js_params))


class FixMyStreetMap(GoogleMap):  
    """
        Overrides the GoogleMap class that comes with GeoDjango.  Optionally,
        show nearby reports.
    """
    def __init__(self,pnt,draggable=False,nearby_reports = [] ):  
#        self.icons = []
        markers = []
        marker = GMarker(geom=(pnt.x,pnt.y), draggable=draggable)
        if draggable:
            event = GEvent('dragend',
                           'function() { window.location.href = "/reports/new?" +"&lat="+geodjango.map_canvas_marker1.getPoint().lat().toString()+"&lon="+geodjango.map_canvas_marker1.getPoint().lng().toString(); }')        
            marker.add_event(event)
        markers.append(marker)
        
        for i in range( len( nearby_reports ) ):
            nearby_marker = ReportMarker(nearby_reports[i], str(i+1) )
            markers.append(nearby_marker)

        GoogleMap.__init__(self,center=(pnt.x,pnt.y),zoom=17,key=settings.GMAP_KEY, markers=markers, dom_id='map_canvas')

class WardMap(GoogleMap):
    """ 
        Show a single ward as a gmap overlay.  Optionally, show reports in the
        ward.
    """
    def __init__(self,ward, reports = []):
        polygons = []
        for poly in ward.geom:
                polygons.append( GPolygon( poly ) )
        markers = []
        for i in range( len( reports ) ):
            marker = ReportMarker(reports[i], str(i+1) )
            markers.append(marker)

        GoogleMap.__init__(self,zoom=13,markers=markers,key=settings.GMAP_KEY, polygons=polygons, dom_id='map_canvas')

           

class CityMap(GoogleMap):
    """
        Show all wards in a city as overlays.
    """
    
    def __init__(self,city):
        polygons = []

        for ward in Ward.objects.filter(city=city):
            for poly in ward.geom:
                polygons.append( GPolygon( poly ) )
        GoogleMap.__init__(self,zoom=13,key=settings.GMAP_KEY, polygons=polygons, dom_id='map_canvas')
    


class GoogleAddressLookup(object):
    
    """
    Simple Google Geocoder abstraction - supports UTF8
 
    >>> doesnt_exist = GoogleAddressLookup("Foobar")
    >>> doesnt_exist.resolve()
    True
    >>> doesnt_exist.exists()
    False

    # Create test matches
    >>> single_match = GoogleAddressLookup("4691 Rue Garnier, Montreal Quebec")
    
    # Check existence
    >>> single_match.resolve()
    True
    >>> single_match.exists()
    True
    >>> single_match.matches_multiple()
    False
    >>> single_match.lat(0)
    '45.5320187'
    >>> single_match.lon(0)
    '-73.5789397'

    # multiple matches
    >>> multiple_matches = GoogleAddressLookup("Beaconsfield")
    >>> multiple_matches.resolve()
    True
    >>> multiple_matches.matches_multiple()
    True
    >>> multiple_matches.get_match_options()
    ['Beaconsfield, QC, Canada', 'Beaconsfield, Buckinghamshire, UK', 'Beaconsfield, St James, NB, Canada', 'Beaconsfield, Andover, NB, Canada', 'Beaconsfield, Norwich, ON, Canada', 'Beaconsfield, Annapolis, Subd. B, NS, Canada', 'Beaconsfield, Withernsea, East Riding of Yorkshire HU19 2, UK', 'Beaconsfield, Stirchley, Telford and Wrekin TF3 1, UK', 'Beaconsfield, Luton LU2 0, UK', 'Beaconsfield TAS, Australia']

    >>> utf8_match = GoogleAddressLookup(u'4691 Rue de Br\xe9beuf Montreal Canada')
    >>> utf8_match.resolve()
    True
    >>> utf8_match.exists()
    True
     """

    def __init__(self,address ):
        self.query_results = []
        self.match_coords = []
        self.xpathContext = None
        self.url = iri_to_uri(u'http://maps.google.ca/maps/geo?q=%s&output=xml&key=%s&oe=utf-8' % (address, settings.GMAP_KEY) )
    
    def resolve(self):
        try:
            resp = urllib.urlopen(self.url).read()
            doc = libxml2.parseDoc(resp)
            self.xpathContext = doc.xpathNewContext()
            self.xpathContext.xpathRegisterNs('google', 'http://earth.google.com/kml/2.0')
            self.query_results = self.xpathContext.xpathEval("//google:coordinates")
            return( True )
        except:
            return( False )
        
    def exists(self):
        return len(self.query_results) != 0 
        
    def matches_multiple(self):
        return len(self.query_results) > 1 
        
    def lat(self, index ):
        coord = self.query_results[index] 
        coord_pair = coord.content.split(',')
        return( coord_pair[1] ) 
        
    def lon(self, index ):
        coord = self.query_results[index] 
        coord_pair = coord.content.split(',')
        return( coord_pair[0] ) 
                        
    def get_match_options(self):
        addr_list = []
        addr_nodes = self.xpathContext.xpathEval("//google:address")
        for i in range(0,len(addr_nodes)):
            addr_list.append(addr_nodes[i].content) 
        return ( addr_list )
    
class SqlQuery(object):
    """
        This is a workaround: django doesn't support our optimized 
        direct SQL queries very well.
    """
        
    def __init__(self):
        self.cursor = None
        self.index = 0
        self.results = None    

    def next(self):
        self.index = self.index + 1
    
    def get_results(self):
        if not self.cursor:
            self.cursor = connection.cursor()
            self.cursor.execute(self.sql)
            self.results = self.cursor.fetchall()
        return( self.results )

class ReportCountQuery(SqlQuery):
      
    def name(self):
        return self.get_results()[self.index][5]

    def recent_new(self):
        return self.get_results()[self.index][0]
    
    def recent_fixed(self):
        return self.get_results()[self.index][1]
    
    def recent_updated(self):
        return self.get_results()[self.index][2]
    
    def old_fixed(self):
        return self.get_results()[self.index][3]
    
    def old_unfixed(self):
        return self.get_results()[self.index][4]
            
    def __init__(self, interval = '1 month'):
        SqlQuery.__init__(self)
        self.base_query = """select count( case when age(clock_timestamp(), reports.created_at) < interval '%s' and reports.is_confirmed THEN 1 ELSE null end ) as recent_new,\
 count( case when age(clock_timestamp(), reports.fixed_at) < interval '%s' AND reports.is_fixed = True THEN 1 ELSE null end ) as recent_fixed,\
 count( case when age(clock_timestamp(), reports.updated_at) < interval '%s' AND reports.is_fixed = False and reports.updated_at != reports.created_at THEN 1 ELSE null end ) as recent_updated,\
 count( case when age(clock_timestamp(), reports.fixed_at) > interval '%s' AND reports.is_fixed = True THEN 1 ELSE null end ) as old_fixed,\
 count( case when age(clock_timestamp(), reports.created_at) > interval '%s' AND reports.is_confirmed AND reports.is_fixed = False THEN 1 ELSE null end ) as old_unfixed   
 """ % (interval,interval,interval,interval,interval) 
        self.sql = self.base_query + " from reports where reports.is_confirmed = true" 

class CityReportCountQuery(ReportCountQuery):

    def __init__(self, city):
        ReportCountQuery.__init__(self,"1 month")
        self.sql = self.base_query 
        field_names = ""
        self.url_prefix = "/wards/"            
        self.sql +=  ", wards.name, wards.id, wards.number from wards "
        self.sql += """left join reports on wards.id = reports.ward_id join cities on wards.city_id = cities.id join province on cities.province_id = province.id
        """
        self.sql += "and cities.id = " + str(city.id)
        self.sql += " group by  wards.name, wards.id, wards.number order by wards.number" 
    
    def number(self):
         return(self.get_results()[self.index][7])
        
    def get_absolute_url(self):
        return( self.url_prefix + str(self.get_results()[self.index][6]))

class CitiesReportCountQuery(ReportCountQuery):

    def __init__(self):
        ReportCountQuery.__init__(self,"1 month")
        self.sql = self.base_query         
        self.url_prefix = "/cities/"            
        self.sql +=  ", cities.name, cities.id, province.name from cities "
        self.sql += """left join wards on wards.city_id = cities.id join province on cities.province_id = province.id left join reports on wards.id = reports.ward_id 
        """ 
        self.sql += "group by cities.name, cities.id, province.name order by province.name, cities.name"
           
    def get_absolute_url(self):
        return( self.url_prefix + str(self.get_results()[self.index][6]))
    
    def province(self):
        return(self.get_results()[self.index][7])
        
    def province_changed(self):
        if (self.index ==0 ):
            return( True )
        return( self.get_results()[self.index][7] != self.get_results()[self.index-1][7] )

class FaqEntry(models.Model):
    __metaclass__ = TransMeta

    q = models.CharField(max_length=100)
    a = models.TextField(blank=True, null=True)
    slug = models.SlugField(null=True, blank=True)
    order = models.IntegerField(null=True, blank=True)
    
    def save(self):
        super(FaqEntry, self).save()
        if self.order == None: 
            self.order = self.id + 1
            super(FaqEntry, self).save()
    
    class Meta:
        db_table = u'faq_entries'
        translate = ('q', 'a', )
       

class FaqMgr(object):
        
    def incr_order(self, faq_entry ):
        if faq_entry.order == 1:
            return
        other = FaqEntry.objects.get(order=faq_entry.order-1)
        swap_order(other[0],faq_entry)
    
    def decr_order(self, faq_entry): 
        other = FaqEntry.objects.filter(order=faq_entry.order+1)
        if len(other) == 0:
            return
        swap_order(other[0],faq_entry)
        
    def swap_order(self, entry1, entry2 ):
        entry1.order = entry2.order
        entry2.order = entry1.order
        entry1.save()
        entry2.save()
 

class PollingStation(models.Model):
    """
    This is a temporary object.  Sometimes, we get maps in the form of
    polling stations, which have to be combined into wards.
    """
    number = models.IntegerField()
    ward_number = models.IntegerField()
    city = models.ForeignKey(City)
    geom = models.MultiPolygonField( null=True)
    objects = models.GeoManager()

    class Meta:
        db_table = u'polling_stations'

