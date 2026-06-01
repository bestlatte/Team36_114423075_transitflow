"""
TransitFlow — Neo4j Seeder
Run once after starting Docker:
    python skeleton/seed_neo4j.py

Loads station and network data from train-mock-data/:
  - metro_stations.json         — city metro stations and adjacencies
  - national_rail_stations.json — national rail stations and adjacencies

Design your graph schema (node labels, relationship types, properties)
based on the data in these files, then implement the seed() function below.
"""

import json
import os
import sys

sys.path.insert(0, ".")

from neo4j import GraphDatabase
from skeleton.config import NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD

_DATA_DIR = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "train-mock-data")
)


def _load(filename):
    with open(os.path.join(_DATA_DIR, filename), encoding="utf-8") as f:
        return json.load(f)


def seed():
    metro_stations = _load("metro_stations.json")
    rail_stations  = _load("national_rail_stations.json")

    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    with driver.session() as session:

        session.run("MATCH (n) DETACH DELETE n")
        print("  Cleared existing graph data")

        # 1. 建立捷運車站節點 (Nodes)
        # 我們給它兩個標籤: :Station 和 :Metro，方便未來查詢
        for s in metro_stations:
            session.run("""
                MERGE (n:Station:Metro {id: $id})
                SET n.name = $name,
                    n.is_interchange_rail = $is_interchange,
                    n.is_closed = false
            """, id=s["station_id"], name=s["name"], is_interchange=s["is_interchange_national_rail"])
        print("  Created Metro nodes")

        # 2. 建立英國鐵路車站節點 (Nodes)
        for s in rail_stations:
            session.run("""
                MERGE (n:Station:NationalRail {id: $id})
                SET n.name = $name,
                    n.is_interchange_metro = $is_interchange,
                    n.is_closed = false
            """, id=s["station_id"], name=s["name"], is_interchange=s.get("is_interchange_metro", False))
        print("  Created National Rail nodes")

        # 3. 建立捷運的連線關係 (Relationships)
        for s in metro_stations:
            for adj in s.get("adjacent_stations", []):
                session.run("""
                    MATCH (a:Station {id: $origin_id})
                    MATCH (b:Station {id: $dest_id})
                    MERGE (a)-[r:CONNECTS_TO {line: $line}]->(b)
                    SET r.travel_time_min = $time,
                        r.standard_fare = 0.5,
                        r.first_class_fare = 0.5
                """, origin_id=s["station_id"], dest_id=adj["station_id"], 
                     line=adj["line"], time=adj["travel_time_min"])
        print("  Created Metro links")

        # 4. 建立鐵路的連線關係 (Relationships)
        for s in rail_stations:
            for adj in s.get("adjacent_stations", []):
                session.run("""
                    MATCH (a:Station {id: $origin_id})
                    MATCH (b:Station {id: $dest_id})
                    MERGE (a)-[r:CONNECTS_TO {line: $line}]->(b)
                    SET r.travel_time_min = $time,
                        r.standard_fare = 1.0,
                        r.first_class_fare = 2.0
                """, origin_id=s["station_id"], dest_id=adj["station_id"], 
                     line=adj["line"], time=adj["travel_time_min"])
        print("  Created National Rail links")

        # 5. 建立跨系統轉乘通道 (Interchange Relationships)
        for s in metro_stations:
            if s.get("is_interchange_national_rail") and s.get("interchange_national_rail_station_id"):
                session.run("""
                    MATCH (m:Metro {id: $m_id})
                    MATCH (r:NationalRail {id: $r_id})
                    MERGE (m)-[:INTERCHANGE {travel_time_min: 5}]->(r)
                    MERGE (r)-[:INTERCHANGE {travel_time_min: 5}]->(m)
                """, m_id=s["station_id"], r_id=s["interchange_national_rail_station_id"])
        print("  Created Interchange links")

    driver.close()
    print("\nNeo4j graph seeded successfully.")
    print("   Open http://localhost:7475 to explore the graph.")


if __name__ == "__main__":
    print("Connecting to Neo4j...")
    seed()
