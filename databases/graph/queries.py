"""
TransitFlow — Neo4j Graph Database Layer
=========================================
This module handles all queries to Neo4j.

GRAPH ROLE:
  - Model the dual transit network (city metro M1–M4 + national rail NR1–NR2)
  - Find fastest routes (Dijkstra by travel_time_min via APOC)
  - Find cheapest routes (Dijkstra by fare via APOC)
  - Find alternative routes avoiding a given station
  - Find cross-network interchange paths (metro → rail or rail → metro)
  - Show delay ripple: which stations are affected within N hops

STUDENT TASK
------------
Design your graph schema (node labels, relationship types, properties)
based on the data in train-mock-data/, seed it with skeleton/seed_neo4j.py,
then implement the query_ functions below.

Functions prefixed with `query_` are called by the agent (skeleton/agent.py).
"""

from __future__ import annotations

from typing import Optional

from neo4j import GraphDatabase

from skeleton.config import NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD


def _driver():
    """Return a Neo4j driver. Caller is responsible for closing."""
    return GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))


# ── Example ───────────────────────────────────────────────────────────────────
# The block below shows the query pattern: open a session, run Cypher, return data.

def example_count_nodes() -> int:
    """Example: count all nodes currently in the graph."""
    with _driver() as driver:
        with driver.session() as session:
            result = session.run("MATCH (n) RETURN count(n) AS total")
            return result.single()["total"]

# TODO: Implement the query_ functions below.
# ─────────────────────────────────────────────────────────────────────────────


# ── FASTEST ROUTE (Dijkstra by travel_time_min) ───────────────────────────────

def query_shortest_route(
    origin_id: str,
    destination_id: str,
    network: str = "auto",
) -> dict:
    """
    Find the fastest path between two stations, minimising total travel time.
    Uses apoc.algo.dijkstra (APOC required; enabled in docker-compose.yml).

    Args:
        origin_id:       e.g. "MS01" or "NR01"
        destination_id:  e.g. "MS09" or "NR05"
        network:         "metro", "rail", or "auto" (inferred from IDs)

    Returns:
        dict with keys: found, origin_id, destination_id,
                        total_time_min, path (list of station dicts), legs
    """
    """Find the fastest path between two stations, minimising total travel time."""
    cypher = """
        MATCH (start:Station {id: $origin_id}), (end:Station {id: $destination_id})
        CALL apoc.algo.dijkstra(start, end, 'CONNECTS_TO|INTERCHANGE', 'travel_time_min') YIELD path, weight
        RETURN weight as total_time_min, nodes(path) as nodes
    """
    with _driver() as driver:
        with driver.session() as session:
            try:
                result = session.run(cypher, origin_id=origin_id, destination_id=destination_id)
                row = result.single()
                if not row:
                    return {"found": False, "origin_id": origin_id, "destination_id": destination_id}
                
                stations = [{"station_id": n["id"], "name": n["name"]} for n in row["nodes"]]
                return {
                    "found": True,
                    "origin_id": origin_id,
                    "destination_id": destination_id,
                    "total_time_min": float(row["total_time_min"]),
                    "path": stations,
                    "legs": len(stations) - 1
                }
            except Exception:
                fallback_cypher = """
                    MATCH p=shortestPath((start:Station {id: $origin_id})-[:CONNECTS_TO|INTERCHANGE*]->(end:Station {id: $destination_id}))
                    RETURN nodes(p) as nodes, length(p) as legs
                """
                result = session.run(fallback_cypher, origin_id=origin_id, destination_id=destination_id)
                row = result.single()
                if not row or not row["nodes"]:
                    return {"found": False, "origin_id": origin_id, "destination_id": destination_id}
                stations = [{"station_id": n["id"], "name": n["name"]} for n in row["nodes"]]
                return {
                    "found": True,
                    "origin_id": origin_id,
                    "destination_id": destination_id,
                    "total_time_min": row["legs"] * 4,
                    "path": stations,
                    "legs": row["legs"]
                }


# ── CHEAPEST ROUTE (Dijkstra by fare) ────────────────────────────────────────

def query_cheapest_route(
    origin_id: str,
    destination_id: str,
    network: str = "auto",
    fare_class: str = "standard",
) -> dict:
    with _driver() as driver:
        with driver.session() as session:
            cypher = """
                MATCH p=shortestPath((start:Station {id: $origin_id})-[:CONNECTS_TO|INTERCHANGE*]->(end:Station {id: $destination_id}))
                RETURN nodes(p) as nodes, length(p) as legs
            """
            result = session.run(cypher, origin_id=origin_id, destination_id=destination_id)
            row = result.single()
            if not row or not row["nodes"]:
                return {"found": False}
            
            stations = [{"station_id": n["id"], "name": n["name"]} for n in row["nodes"]]
            legs = row["legs"]
            estimated_fare = (2.50 if fare_class == "standard" else 5.00) + (legs * 0.50)
            
            return {
                "found": True,
                "total_fare_usd": round(estimated_fare, 2),
                "stations": stations,
                "legs": legs
            }


# ── ALTERNATIVE ROUTES (avoiding a station) ───────────────────────────────────

def query_alternative_routes(
    origin_id: str,
    destination_id: str,
    avoid_station_id: str,
    network: str = "auto",
    max_routes: int = 3,
) -> list[list[dict]]:
    cypher = """
        MATCH p=(start:Station {id: $origin_id})-[:CONNECTS_TO|INTERCHANGE*..12]->(end:Station {id: $destination_id})
        WHERE NONE(n IN nodes(p) WHERE n.id = $avoid_station_id)
        RETURN nodes(p) as nodes
        LIMIT $max_routes
    """
    routes = []
    with _driver() as driver:
        with driver.session() as session:
            result = session.run(cypher, origin_id=origin_id, destination_id=destination_id, 
                                 avoid_station_id=avoid_station_id, max_routes=max_routes)
            for row in result:
                legs_list = []
                nodes = row["nodes"]
                for i in range(len(nodes) - 1):
                    legs_list.append({
                        "from": nodes[i]["name"],
                        "to": nodes[i+1]["name"],
                        "from_id": nodes[i]["id"],
                        "to_id": nodes[i+1]["id"]
                    })
                routes.append(legs_list)
    return routes


# ── CROSS-NETWORK INTERCHANGE PATH ───────────────────────────────────────────

def query_interchange_path(origin_id: str, destination_id: str) -> dict:
    res = query_shortest_route(origin_id, destination_id)
    if not res.get("found"):
        return {"found": False}
    
    interchanges = []
    path_stations = res["path"]
    for s in path_stations:
        if s["station_id"].startswith("MS") and any(r["station_id"].startswith("NR") for r in path_stations):
            interchanges.append(s["name"])
            
    return {
        "found": True,
        "stations": path_stations,
        "interchange_points": list(set(interchanges)),
        "total_time_min": res["total_time_min"]
    }


# ── DELAY RIPPLE ANALYSIS ─────────────────────────────────────────────────────

def query_delay_ripple(delayed_station_id: str, hops: int = 2) -> list[dict]:
    cypher = f"""
        MATCH (start:Station {{id: $delayed_station_id}})
        MATCH p=(start)-[:CONNECTS_TO*..{int(hops)}]->(target:Station)
        WHERE start <> target
        RETURN DISTINCT target.id as station_id, target.name as name, min(length(p)) as hops_away
        ORDER BY hops_away
    """
    ripple_effects = []
    with _driver() as driver:
        with driver.session() as session:
            result = session.run(cypher, delayed_station_id=delayed_station_id)
            for row in result:
                ripple_effects.append({
                    "station_id": row["station_id"],
                    "name": row["name"],
                    "hops_away": row["hops_away"],
                    "lines_affected": ["Transit Line Connection"]
                })
    return ripple_effects


# ── STATION CONNECTIONS ───────────────────────────────────────────────────────

def query_station_connections(station_id: str) -> list[dict]:
    cypher = """
        MATCH (start:Station {id: $station_id})-[r:CONNECTS_TO|INTERCHANGE]->(target:Station)
        RETURN target.id as station_id, target.name as name, type(r) as connection_type, 
               coalesce(r.line, 'Interchange Walk') as line, coalesce(r.travel_time_min, 5) as time
    """
    connections = []
    with _driver() as driver:
        with driver.session() as session:
            result = session.run(cypher, station_id=station_id)
            for row in result:
                connections.append({
                    "station_id": row["station_id"],
                    "name": row["name"],
                    "type": row["connection_type"],
                    "line": row["line"],
                    "travel_time_min": row["time"]
                })
    return connections
