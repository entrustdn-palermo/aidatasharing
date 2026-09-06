"""
Connector type configurations and document processor registry.
Extracted from ConnectorService for focused responsibility.
"""

SUPPORTED_CONNECTORS = {
    'mysql': {
        'required_config': ['host', 'port', 'database'],
        'required_credentials': ['user', 'password'],
        'optional_config': ['charset', 'ssl_disabled'],
        'default_port': 3306
    },
    'postgresql': {
        'required_config': ['host', 'port', 'database'],
        'required_credentials': ['user', 'password'],
        'optional_config': ['sslmode', 'connect_timeout'],
        'default_port': 5432
    },
    's3': {
        'required_config': ['bucket_name', 'region'],
        'required_credentials': ['aws_access_key_id', 'aws_secret_access_key'],
        'optional_config': ['endpoint_url', 'prefix'],
        'default_region': 'us-east-1'
    },
    'mongodb': {
        'required_config': ['host', 'port', 'database'],
        'required_credentials': ['username', 'password'],
        'optional_config': ['authSource', 'ssl'],
        'default_port': 27017
    },
    'snowflake': {
        'required_config': ['account', 'warehouse', 'database', 'schema'],
        'required_credentials': ['user', 'password'],
        'optional_config': ['role', 'timeout'],
        'default_schema': 'PUBLIC'
    },
    'bigquery': {
        'required_config': ['project_id', 'dataset_id'],
        'required_credentials': ['service_account_json'],
        'optional_config': ['location'],
        'default_location': 'US'
    },
    'redshift': {
        'required_config': ['host', 'port', 'database'],
        'required_credentials': ['user', 'password'],
        'optional_config': ['sslmode'],
        'default_port': 5439
    },
    'clickhouse': {
        'required_config': ['host', 'port', 'database'],
        'required_credentials': ['user', 'password'],
        'optional_config': ['secure', 'verify'],
        'default_port': 8123
    },
    'api': {
        'required_config': ['base_url', 'endpoint'],
        'required_credentials': [],
        'optional_config': ['headers', 'auth_type', 'timeout'],
        'default_timeout': 30
    },
    'file_system': {
        'required_config': ['path'],
        'required_credentials': [],
        'optional_config': ['file_pattern', 'recursive'],
        'default_recursive': False
    }
}

DOCUMENT_PROCESSORS = {
    'pdf': '_process_pdf_document',
    'docx': '_process_docx_document',
    'doc': '_process_doc_document',
    'txt': '_process_txt_document',
    'rtf': '_process_rtf_document',
    'odt': '_process_odt_document',
}
