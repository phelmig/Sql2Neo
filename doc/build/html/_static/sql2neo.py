#!/opt/local/bin/python
import MySQLdb
from py2neo import cypher
from py2neo import neo4j
import datetime
import calendar

class sql2NeoRelationship(object):
	"""sql2NeoRelationship a SQL relationship that will be migrated to Neo4j. The name defines the relationship name in Neo4j and does not have to be unique. Upper case Strings without special characters except for '_' are enforced.
	"""
	name=""
	""" defines the relationship name in Neo4j and does not have to be unique. Upper case Strings without special characters except for '_' are enforced."""
	leftEntity=None
	"""Left hand side entity of all Relationships"""
	rightEntitiy=None
	"""Right hand side entity of all Relationships"""
	query=""
	"""SQL Query to recieve all relationships that have to be migrated. Joins can be used to replace ids with an identifier that is available in Neo4j"""
	lookupMapping=[{},{}]
	"""An array of two dictionaries defining which properties are used to lookup the nodes that will be connected. The first dictionary declares the lookup for the left entity, the second one for the right one. the value for each entry has to be the index of the value in query that is to be used for the lookup. E.g. name and age should be used and will be returned in this order by *query* the mapping would be [{'name':0},{'age':1}]"""
	cursor=None
	"""Current mysql cursor"""
	results=-1
	"""Result count of the last query executed"""
	importer=None
	"""The importer handling this relationship, will be set as the relationship is added to a sql2NeoImporter"""
	def __init__(self, name, leftEntity, rightEntitiy, query,lookupMapping):
		"""sql2NeoRelationship a SQL relationship that will be migrated to Neo4j. The name defines the relationship name in Neo4j and does not have to be unique. Upper case Strings without special characters except for '_' are enforced.
		"""
		self.name=name
		self.leftEntity=leftEntity
		self.rightEntitiy=rightEntitiy
		self.query=query
		self.lookupMapping=lookupMapping

	def execute(self,sqlConnection):
		"""executes *query* and returns the results (or -1 if it fails)
		"""
		try:
			self.cursor=sqlConnection.cursor()
			self.results=self.cursor.execute(self.query)
			return self.results
		except MySQLdb.Error as e:
				print "Can not execute query: '{0}' for relationship '{1}': \n--\n{2}\n--".format(self.query,self.name,str(e))
				return -1

	def getMappedLookup(self,row):
		"""Returns a mapped instance of the result (MySQLdb row) row is expected to be a row from the last execute"""
		ret=[]
		for i in xrange(2):
			# 0 => left; 1=> right
			m={}
			for l in self.lookupMapping[i]:
				m[l]=self.importer.convertDataType(row[self.lookupMapping[i][l]])
			ret.append(m)
		return ret

	def buildCreateQuery(self,mappedLookup):
		"""Builds a Cypher query to create a relationship from a mapped sql lookup. NOTE: The corresponding entites have to be imported first"""
		return "MATCH (a:{0} {{{1}}}),(b:{2} {{{3}}}) CREATE (a)-[:{4}]->(b)".format(self.leftEntity.name,self.importer.mappedToCypher(mappedLookup[0]),self.rightEntitiy.name,self.importer.mappedToCypher(mappedLookup[1]),self.name)



class sql2NeoEntity(object):
	"""sql2NeoEntity defines a SQL entity that will be migrated to Neo4j. The name defines the name this entity will be labeled with in neo4j. Query must contain a SQL query which returns **all** items of this entity in the sql database. Joins and data conversions are allowed in the query. pMapping is a simple mapping of column index of the query result to Neo4j property names. Set autoMap to true to automaticall migrate not mapped items using the mysql column name
	"""
	name=""					
	"""Will be used for the Neo4j label as well"""
	query=""				
	"""SQL Query used for export """
	results=-1
	"""number of results will be written by itlImporter"""
	propertyMapping={}
	"""index in the sql result => Neo4j porperty name"""
	autoMap=False
	"""Migrate not mapped fields using the SQL column name"""
	indexes=[]
	"""List of properties to be indexed"""
	uniques=[]
	"""List of properties to be unique"""
	importer=None
	"""The importer handling this entity, will be set as the entity is added to a sql2NeoImporter"""
	def __init__(self,name, query, pMapping,idx=[],unq=[]):
		"""The name defines the name this entity will be labeled with in neo4j. Query must contain a SQL query which returns **all** items of this entity in the sql database. Joins and data conversions are allowed in the query. pMapping is a simple mapping of column index of the query result to Neo4j property names """
		self.name=name
		self.query=query
		self.propertyMapping=pMapping
		self.indexes=idx
		self.uniques=unq

	def getMappedEntity(self,row):
		"""Returns a mapped instance of the result (MySQLdb row)
		row is expected to be a row from the last query of the last execute
		"""
		ret={}
		description=self.cursor.description
		for i in xrange(len(description)):
			if self.propertyMapping.has_key(i):
				ret[self.propertyMapping[i]]=self.importer.convertDataType(row[i])
			else:
				if self.autoMap:
					ret[description[i][0]]=self.importer.convertDataType(row[i])
		return ret

	
	def buildCreateQuery(self,mappedEntity):
		"""Builds a Cypher query to create a node from a mapped sql entity"""
		return "CREATE (a:{0} {{{1}}})".format(self.name,self.importer.mappedToCypher(mappedEntity))

	def execute(self,sqlConnection):
		"""executes *query* and returns the results (or -1 if it fails)
		"""
		try:
			self.cursor=sqlConnection.cursor()
			self.results=self.cursor.execute(self.query)
			return self.results
		except MySQLdb.Error as e:
				print "Can not execute query: '{0}' for entity '{1}': \n--\n{2}\n--".format(self.query,self.name,str(e))
				return -1
		

class sql2NeoImporter(object):
	"""sql2NeoImporter allows the import of SQL databases to Neo4j currently Entities (Data tables) and Relationships (Tables and foreign keys) are supported. 
	"""
	sqlConnection=None
	"""SQL Connection (MySQLdb)"""
	neo4jConnection=None
	"""Neo4j Connection (py2neo)"""
	entities=[]
	"""List of entities to migrate"""
	relationships=[]
	"""List of relationships to migrate"""
	def initSqlConnection(self, config):
		"""Connect to a MySQL Server. Currently used: config.HOST, config.USER, config.PWD, config.DB  
		"""
		try:
			self.sqlConnection=MySQLdb.connect(host=config.HOST, 
				user=config.USER,	
				passwd=config.PWD, 
				db=config.DB)
		except MySQLdb.Error as e:
			print "Can not connect to MySQL: %s" % str(e)

	def initNeo4jConnection(self, config):
		"""Connect to a Neo4j Server config.URL is expected to be the URL to a connectable Server. For example: http://localhost:7474/db/data/
		"""
		try:
			self.neo4jConnection=cypher.Session(config.URL)
		except (neo4j.ClientError, neo4j.ServerError) as e:
			print "Can not connect to Neo4j: %s" % str(e)

	def __init__(self, sqlConfig, neo4jConfig):
		self.initSqlConnection(sqlConfig)
		self.initNeo4jConnection(neo4jConfig)

	notChangingTypes=[int, float, str,long]
	"""Python types that will be kept when importing into Neo4j"""
	convertedTypes=[datetime.time, datetime.datetime, datetime.date,datetime.timedelta,type(None)]
	"""Types that will be converted in *convertedTypes*"""
	def convertDataType(self,data):
		"""Converts a datatype recieved from SQL to a Neo4j compatible type. Especially DateTime Types have to be converted to Unix timestamps. Not implemented/unknown types will throw an *TypeNotImplemented* or *TypeNotCompatible* exception. Returns the data converted to the new type"""
		t = type(data)
		if t in self.notChangingTypes:
			return data
		if t in self.convertedTypes:
			if t==datetime.time:
				return str(data)		# str
			if t==datetime.timedelta:
				return str(data)		# str
			if t==datetime.datetime:
				return calendar.timegm(data.timetuple()) # UTC unix timestamp (int)
			if t==datetime.date:
				return calendar.timegm(data.timetuple()) # UTC unix timestamp (int)
			if t==type(None):
				return ''				# str

		raise self.TypeNotImplemented(t)

	class TypeNotImplemented(Exception):
		def __init__(self,type):
			self.value = str(type) + " not implemented"
		def __str__(self):
			return repr(self.value)
	
	class TypeNotCompatible(Exception):
		def __init__(self,type):
			self.value = str(type) + " not compatible with Neo4j"
		def __str__(self):
			return repr(self.value)		

	def escapeCypher(self, s):
		"""Escapes a cypher string, currently only escapes ' -> \' """
		return s.replace("'","\\'")
	
	def mappedToCypher(self, mappedEntity):
		"""Creates a Cypher query to insert a mapped entity into the graph"""
		data=""
		for el in mappedEntity:
			if type(mappedEntity[el])==str:
				data+="{0}:'{1}',".format(el,self.escapeCypher( mappedEntity[el]))
			else:
				data+="{0}:{1},".format(el,mappedEntity[el])
		data=data[:-1]
		return data
	
	def addEntity(self,e):
		"""Add a sql2NeoEntity to the importer job
		"""
		self.entities.append(e)
		e.importer=self

	def addRelationship(self,r):
		"""Add a sql2NeoRelationship to the importer job
		"""
		self.relationships.append(r)
		r.importer=self

	def testEntities(self):
		"""Tests all entity queries and prints out the first result of the query as well as the corresponding generated Cypher query. """
		for e in self.entities:
			print "Testing entity: %s" % str(e.name)
			print "Result Counts: %s" % str(e.execute(self.sqlConnection))
			row=e.cursor.fetchone()
			print "Sql Row: %s" % str(row)
			print "Mapped row: %s" % str(e.getMappedEntity(row))
			print "Cypher insert: %s" % str(e.buildCreateQuery(e.getMappedEntity(row)))
			print 

	def testRelationships(self):
		"""Tests all relationship queries and prints out the first result of the query as well as the corresponding generated Cypher query. """
		for r in self.relationships:
			print "Testing entity: %s" % str(r.name)
			print "Result Counts: %s" % str(r.execute(self.sqlConnection))
			row=r.cursor.fetchone()
			print "Sql Row: %s" % str(row)
			print r.buildCreateQuery(r.getMappedLookup(row))
			print ""


	def createIndexes(self):
		"""Creates and executes the cypher queries for all entities' indexes. Returns True on sucesss and False on error"""
		tx=self.neo4jConnection.create_transaction()
		for e in self.entities:
			print "Creating Indexes for {0}...".format(e.name)
			for i in e.indexes:
				q="CREATE INDEX ON :{0}({1})".format(e.name,i)
				print q
				tx.append(q)
		try:
			tx.commit()
			return True
		except (neo4j.ClientError, neo4j.ServerError,neo4j.CypherError,cypher.TransactionError) as e:
			print "Can not create indexes: {0}".format(str(e))
			return False
			
	def createUniques(self):
		"""Creates and executes the cypher queries for all entities' unique constraints. Returns True on sucesss and False on error"""
		tx=self.neo4jConnection.create_transaction()
		for e in self.entities:
			print "Creating Uniques for {0}...".format(e.name)
			for u in e.uniques:
				q="CREATE CONSTRAINT ON (p:{0}) ASSERT p.{1} IS UNIQUE".format(e.name,u)
				print q
				tx.append(q)
		try:
			tx.commit()
			return True
		except (neo4j.ClientError, neo4j.ServerError,neo4j.CypherError,cypher.TransactionError) as e:
			print "Can not create indexes: {0}".format(str(e))
			return False

	def importEntites(self,textOnly=True):
		"""Imports all entities. Returns True on success and False on error"""
		if(not textOnly):
			tx=self.neo4jConnection.create_transaction()
		for e in self.entities:
			print "Inserting {0} instances of entity {1}".format(e.execute(self.sqlConnection),e.name)
			for row in e.cursor:
				if(textOnly):
					print str(e.buildCreateQuery(e.getMappedEntity(row)))
				else:
					tx.append(str(e.buildCreateQuery(e.getMappedEntity(row))))
		if(not textOnly):
			try:
				tx.commit()
				return True
			except (neo4j.ClientError, neo4j.ServerError,neo4j.CypherError,cypher.TransactionError) as e:
				print "Can not import entities: {0}".format(str(e))
				return False
			
	def importRelationships(self,textOnly=True):
		"""Imports all relationships. Returns True on success and False on error"""
		if(not textOnly):
			tx=self.neo4jConnection.create_transaction()
		for r in self.relationships:
			print "Inserting {0} relationships of type {1}".format(r.execute(self.sqlConnection),r.name)
			for row in r.cursor:
				if(textOnly):
					print str(r.buildCreateQuery(r.getMappedLookup(row)))
				else:
					tx.append(str(r.buildCreateQuery(r.getMappedLookup(row))))
		if(not textOnly):
			try:
				tx.commit()
				return True
			except (neo4j.ClientError, neo4j.ServerError,neo4j.CypherError,cypher.TransactionError) as e:
				print "Can not import relationships: {0}".format(str(e))
				return False

