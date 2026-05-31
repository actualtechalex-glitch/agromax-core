import os
import sys
import logging
from dotenv import load_dotenv
from neo4j import GraphDatabase
from neo4j.exceptions import Neo4jError

# Configure logging to write to neo4j_log.txt, overwrite each run
LOG_FILE = "neo4j_log.txt"
logging.basicConfig(
    filename=LOG_FILE,
    filemode="w",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    encoding="utf-8"
)

def main():
    logging.info("Starting Neo4j connection check script...")
    
    # Load environment variables from .env
    load_dotenv()
    
    uri = os.getenv("NEO4J_URI")
    print(f"DEBUG: os.getenv('NEO4J_URI') = {uri}")
    user = os.getenv("NEO4J_USER")
    password = os.getenv("NEO4J_PASSWORD")
    
    if not uri or not user or not password:
        logging.error(
            "Missing environment variables. Please ensure NEO4J_URI, "
            "NEO4J_USER, and NEO4J_PASSWORD are set in the .env file."
        )
        sys.exit(1)
        
    logging.info(f"Connecting to Neo4j at {uri} as user '{user}'...")
    
    driver = None
    try:
        # Initialize driver
        driver = GraphDatabase.driver(uri, auth=(user, password))
        
        # Test connection by verifying connectivity
        driver.verify_connectivity()
        logging.info("Successfully connected and verified connectivity to the server.")
        
        # Open session to perform operations
        with driver.session() as session:
            # 1. Create a test node
            logging.info("Creating test node...")
            create_query = "CREATE (t:TestConnection {status: $status}) RETURN id(t) AS node_id, t.status AS status"
            result = session.run(create_query, status="Success")
            record = result.single()
            if record:
                node_id = record["node_id"]
                node_status = record["status"]
                logging.info(f"Created node with ID {node_id} and status '{node_status}'.")
            else:
                logging.error("Failed to create test node.")
                sys.exit(1)
                
            # 2. Read the test node to verify
            logging.info("Reading test node to verify...")
            read_query = "MATCH (t:TestConnection {status: $status}) RETURN id(t) AS node_id, t.status AS status"
            result = session.run(read_query, status="Success")
            records = list(result)
            logging.info(f"Found {len(records)} node(s) with status 'Success'.")
            for rec in records:
                logging.info(f"Verified node: ID {rec['node_id']}, status '{rec['status']}'.")
                
            # 3. Delete the test node
            logging.info("Deleting test node...")
            delete_query = "MATCH (t:TestConnection {status: $status}) DETACH DELETE t"
            result = session.run(delete_query, status="Success")
            summary = result.consume()
            nodes_deleted = summary.counters.nodes_deleted
            logging.info(f"Deleted {nodes_deleted} test node(s). Cleanup complete.")
            
        logging.info("All connection tests completed successfully.")
        
    except Neo4jError as ne:
        logging.error(f"Neo4j database error: {ne}")
        sys.exit(1)
    except Exception as e:
        logging.error(f"Unexpected error: {e}")
        sys.exit(1)
    finally:
        if driver:
            driver.close()
            logging.info("Connection driver closed.")

if __name__ == "__main__":
    main()
