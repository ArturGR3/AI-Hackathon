import logging
import time
from typing import Any, List, Optional, Tuple, Union
from datetime import datetime

import pandas as pd
from DB.app.config.settings import get_settings
from openai import OpenAI
from timescale_vector import client
import psycopg2
from psycopg2.extras import RealDictCursor


class VectorStore:
    """A class for managing vector operations and database interactions."""

    def __init__(self):
        """Initialize the VectorStore with settings, OpenAI client, and Timescale Vector client."""
        self.settings = get_settings()
        self.openai_client = OpenAI(api_key=self.settings.openai.api_key)
        self.embedding_model = self.settings.openai.embedding_model
        self.vector_settings = self.settings.vector_store
        self.vec_client = client.Sync(
            self.settings.database.service_url,
            self.vector_settings.table_name,
            self.vector_settings.embedding_dimensions,
            time_partition_interval=self.vector_settings.time_partition_interval,
        )

    def get_embedding(self, text: str) -> List[float]:
        """
        Generate embedding for the given text.

        Args:
            text: The input text to generate an embedding for.

        Returns:
            A list of floats representing the embedding.
        """
        text = text.replace("\n", " ")
        start_time = time.time()
        embedding = (
            self.openai_client.embeddings.create(
                input=[text],
                model=self.embedding_model,
            )
            .data[0]
            .embedding
        )
        elapsed_time = time.time() - start_time
        logging.info(f"Embedding generated in {elapsed_time:.3f} seconds")
        return embedding

    def create_tables(self) -> None:
        """Create the necessary tablesin the database"""
        self.vec_client.create_tables()

    def create_index(self) -> None:
        """Create the StreamingDiskANN index to speed up similarity search if it doesn't exist."""
        try:
            self.vec_client.create_embedding_index(client.DiskAnnIndex())
            logging.info("Successfully created StreamingDiskANN index")
        except Exception as e:
            if "already exists" in str(e):
                logging.info("Index already exists, skipping creation")
            else:
                raise e

    def drop_index(self) -> None:
        """Drop the StreamingDiskANN index in the database"""
        self.vec_client.drop_embedding_index()

    def upsert(self, df: pd.DataFrame) -> None:
        """
        Insert or update records in the database from a pandas DataFrame.

        Args:
            df: A pandas DataFrame containing the data to insert or update.
                Expected columns: id, metadata, contents, embedding
        """
        records = df.to_records(index=False)
        self.vec_client.upsert(list(records))
        logging.info(
            f"Inserted {len(df)} records into {self.vector_settings.table_name}"
        )

    def search(
        self,
        query_text: str,
        limit: int = 5,
        metadata_filter: Union[dict, List[dict]] = None,
        predicates: Optional[client.Predicates] = None,
        time_range: Optional[Tuple[datetime, datetime]] = None,
        return_dataframe: bool = True,
    ) -> Union[List[Tuple[Any, ...]], pd.DataFrame]:
        """
        Query the vector database for similar embeddings based on input text.

        More info:
            https://github.com/timescale/docs/blob/latest/ai/python-interface-for-pgvector-and-timescale-vector.md

        Args:
            query_text: The input text to search for.
            limit: The maximum number of results to return.
            metadata_filter: A dictionary or list of dictionaries for equality-based metadata filtering.
            predicates: A Predicates object for complex metadata filtering.
                - Predicates objects are defined by the name of the metadata key, an operator, and a value.
                - Operators: ==, !=, >, >=, <, <=
                - & is used to combine multiple predicates with AND operator.
                - | is used to combine multiple predicates with OR operator.
            time_range: A tuple of (start_date, end_date) to filter results by time.
            return_dataframe: Whether to return results as a DataFrame (default: True).

        Returns:
            Either a list of tuples or a pandas DataFrame containing the search results.

        Basic Examples:
            Basic search:
                vector_store.search("What are your shipping options?")
            Search with metadata filter:
                vector_store.search("Shipping options", metadata_filter={"category": "Shipping"})
        
        Predicates Examples:
            Search with predicates:
                vector_store.search("Pricing", predicates=client.Predicates("price", ">", 100))
            Search with complex combined predicates:
                complex_pred = (client.Predicates("category", "==", "Electronics") & client.Predicates("price", "<", 1000)) | \
                               (client.Predicates("category", "==", "Books") & client.Predicates("rating", ">=", 4.5))
                vector_store.search("High-quality products", predicates=complex_pred)
        
        Time-based filtering:
            Search with time range:
                vector_store.search("Recent updates", time_range=(datetime(2024, 1, 1), datetime(2024, 1, 31)))
        """
        query_embedding = self.get_embedding(query_text)

        start_time = time.time()

        search_args = {
            "limit": limit,
        }

        if metadata_filter:
            search_args["filter"] = metadata_filter

        if predicates:
            search_args["predicates"] = predicates

        if time_range:
            start_date, end_date = time_range
            search_args["uuid_time_filter"] = client.UUIDTimeRange(start_date, end_date)

        results = self.vec_client.search(query_embedding, **search_args)
        elapsed_time = time.time() - start_time

        logging.info(f"Vector search completed in {elapsed_time:.3f} seconds")

        if return_dataframe:
            return self._create_dataframe_from_results(results)
        else:
            return results

    def _create_dataframe_from_results(
        self,
        results: List[Tuple[Any, ...]],
    ) -> pd.DataFrame:
        """
        Create a pandas DataFrame from the search results.

        Args:
            results: A list of tuples containing the search results.

        Returns:
            A pandas DataFrame containing the formatted search results.
        """
        # Convert results to DataFrame
        df = pd.DataFrame(
            results, columns=["id", "metadata", "content", "embedding", "distance"]
        )

        # Expand metadata column
        df = pd.concat(
            [df.drop(["metadata"], axis=1), df["metadata"].apply(pd.Series)], axis=1
        )

        # Convert id to string for better readability
        df["id"] = df["id"].astype(str)

        return df

    def delete(
        self,
        ids: List[str] = None,
        metadata_filter: dict = None,
        delete_all: bool = False,
    ) -> None:
        """Delete records from the vector database.

        Args:
            ids (List[str], optional): A list of record IDs to delete.
            metadata_filter (dict, optional): A dictionary of metadata key-value pairs to filter records for deletion.
            delete_all (bool, optional): A boolean flag to delete all records.

        Raises:
            ValueError: If no deletion criteria are provided or if multiple criteria are provided.

        Examples:
            Delete by IDs:
                vector_store.delete(ids=["8ab544ae-766a-11ef-81cb-decf757b836d"])

            Delete by metadata filter:
                vector_store.delete(metadata_filter={"category": "Shipping"})

            Delete all records:
                vector_store.delete(delete_all=True)
        """
        if sum(bool(x) for x in (ids, metadata_filter, delete_all)) != 1:
            raise ValueError(
                "Provide exactly one of: ids, metadata_filter, or delete_all"
            )

        if delete_all:
            self.vec_client.delete_all()
            logging.info(f"Deleted all records from {self.vector_settings.table_name}")
        elif ids:
            self.vec_client.delete_by_ids(ids)
            logging.info(
                f"Deleted {len(ids)} records from {self.vector_settings.table_name}"
            )
        elif metadata_filter:
            self.vec_client.delete_by_metadata(metadata_filter)
            logging.info(
                f"Deleted records matching metadata filter from {self.vector_settings.table_name}"
            )

    def drop_tables(self) -> None:
        """Drop the existing tables in the database"""
        self.vec_client.drop_table()

    def tables_exist(self) -> bool:
        """
        Check if the vector store tables exist in the database.
        
        Returns:
            bool: True if tables exist, False otherwise
        """
        try:
            # Try to execute a simple query to check if the table exists
            self.vec_client.execute_sql(
                f"SELECT 1 FROM {self.vector_settings.table_name} LIMIT 1"
            )
            return True
        except Exception:
            return False

    def verify_record_exists(self, record_id: str) -> bool:
        """
        Verify that a record exists in the database.
        
        Args:
            record_id: The ID of the record to verify
            
        Returns:
            bool: True if record exists, False otherwise
        """
        try:
            # Create a direct connection to PostgreSQL
            conn = psycopg2.connect(self.settings.database.service_url)
            with conn.cursor() as cur:
                cur.execute(
                    f"SELECT 1 FROM {self.vector_settings.table_name} WHERE id = %s",
                    (record_id,)
                )
                result = cur.fetchone()
            conn.close()
            return bool(result)
        except Exception as e:
            logging.error(f"Error verifying record: {e}")
            return False

    def get_record_count(self) -> int:
        """
        Get the total number of records in the database.
        
        Returns:
            int: Number of records in the database
        """
        try:
            conn = psycopg2.connect(self.settings.database.service_url)
            with conn.cursor() as cur:
                cur.execute(f"SELECT COUNT(*) FROM {self.vector_settings.table_name}")
                result = cur.fetchone()
            conn.close()
            return result[0] if result else 0
        except Exception as e:
            logging.error(f"Error getting record count: {e}")
            return 0

    def verify_connection(self) -> bool:
        """
        Verify that the database connection is working.
        
        Returns:
            bool: True if connection is working, False otherwise
        """
        try:
            # Create a direct connection to PostgreSQL
            conn = psycopg2.connect(self.settings.database.service_url)
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
            conn.close()
            return True
        except Exception as e:
            logging.error(f"Database connection error: {e}")
            return False

    def get_connection_info(self) -> dict:
        """
        Get information about the current database connection.
        
        Returns:
            dict: Connection information including version, tables, and indexes
        """
        info = {
            "connected": False,
            "version": None,
            "tables": [],
            "indexes": []
        }
        
        try:
            # Create a direct connection to PostgreSQL
            conn = psycopg2.connect(self.settings.database.service_url)
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # Check if connected
                info["connected"] = True
                
                # Get PostgreSQL version
                cur.execute("SHOW server_version")
                version = cur.fetchone()
                info["version"] = version['server_version'] if version else None
                
                # Get existing tables
                cur.execute("""
                    SELECT table_name 
                    FROM information_schema.tables 
                    WHERE table_schema = 'public'
                """)
                info["tables"] = [record['table_name'] for record in cur.fetchall()]
                
                # Get existing indexes
                cur.execute("""
                    SELECT indexname 
                    FROM pg_indexes 
                    WHERE schemaname = 'public'
                """)
                info["indexes"] = [record['indexname'] for record in cur.fetchall()]
                
            conn.close()
        except Exception as e:
            logging.error(f"Error getting connection info: {e}")
            
        return info
