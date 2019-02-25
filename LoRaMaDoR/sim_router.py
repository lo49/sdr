#!/usr/bin/env python3

# LoRaMaDoR (LoRa-based mesh network for hams) project
# Mesh network simulator / routing algorithms testbed
# Copyright (c) 2019 PU5EPX

import random, asyncio, sys, time
from sim_packet import Packet

ROUTER_VERBOSITY = 100

CAN_DIFFUSE_UNKNOWN = True
CAN_DIFFUSE_NOROUTE = True

class Router:
	def __init__(self, callsign, helper):
		self.callsign = callsign
		self.edges = {}
		self.sent_edges = {}
		self.helper = helper
		self.routines = [ MeshFormation(self.callsign, self.helper) ]
		self.cache = {}

		async def probe():
			while True:
				await asyncio.sleep(120 + random.random() * 60)
				now = time.time()
				expired = []
				for to, x in self.cache.items():
					for fr0m, y in x.items():
						via, cost, timestamp = y
						if (now - timestamp) > 120:
							expiry = (to, via, fr0m)
				for to, via, fr0m in expired:
					if ROUTER_VERBOSITY > 90:
						print("%s rt: expiring cached %d < %d < %d" % \
							(to, via, fr0m))
					del self.cache[to][fr0m]
		loop.create_task(probe())

	def learn(self, ident, ttl, path, last_hop_rssi):
		# Extract graph edges from breadcrumb path
		if not path:
			return

		if ttl >= 0:
			# path[0] is neighbor
			path = [ self.callsign ] + path

		if ROUTER_VERBOSITY > 90:
			print("%s rt: learning path %s ident %s ttl %d" \
				% (self.callsign, " < ".join(path), ident, ttl))

		for i in range(0, len(path) - 1):
			to = path[i]
			fr0m = path[i+1]
			# print("#### %s %s %s" % (str(path), to, fr0m))

			if to == fr0m:
				print("#### FATAL %s <- %s" % (to, fr0m))
				sys.exit(1)

			cost = 1000
			if i == 0:
				# Cost of adjacent node = -RSSI
				cost = -last_hop_rssi

			# FIXME cost not being propagated

			if to not in self.edges:
				self.edges[to] = {}
				self.sent_edges[to] = {}

			if fr0m not in self.edges[to]:
				self.edges[to][fr0m] = cost
				self.sent_edges[to][fr0m] = False
				if ROUTER_VERBOSITY > 50:
					print("%s rt: learnt edge %s < %s" % \
						(self.callsign, to, fr0m))

			elif self.edges[to][fr0m] > cost:
				self.edges[to][fr0m] = cost
				if ROUTER_VERBOSITY > 50:
					print("%s rt: reduced cost %s < %s" % \
						(self.callsign, to, fr0m))

		if ROUTER_VERBOSITY >= 50:
			learnt_edges = sum(len(v.keys()) for k, v in self.edges.items())
			total_edges = self.helper['total_edges']()
			pp = 100 * learnt_edges / total_edges
			print("%s rt knows %.1f%%" % (self.callsign, pp))
			# print("\tknows: ", self.edges)

	def prune(self, left_is_us, path):
		# Remove heading and trailing edges that we have already published
		# NOTE: assume that path was already learn()ed
		path_before = path[:]
		path = path[:]

		if ROUTER_VERBOSITY > 90:
			print("%s rt: pruning path %s" % (self.callsign, " < ".join(path)))

		if left_is_us:
			# Cannot prune at left because of guarantee that
			# path[0] == ourselves when ttl >= 0
			pass
		else:
			# Prune at left
			while len(path) >= 2:
				to = path[0]
				fr0m = path[1]
				if self.sent_edges[to][fr0m]:
					# Already sent, prune
					path = path[1:]
					if ROUTER_VERBOSITY > 90:
						print("%s rt: pruned edge %s < %s" % \
							(self.callsign, to, fr0m))
				else:
					break
	
		# Prune at right
		while len(path) >= 2:
			to = path[-2]
			fr0m = path[-1]
			if self.sent_edges[to][fr0m]:
				# Already sent, prune
				path = path[:-1]
				if ROUTER_VERBOSITY > 90:
					print("%s rt: pruned edge %s < %s" % \
						(self.callsign, to, fr0m))
			else:
				break
		
		if len(path) < 2:
			path = []

		if ROUTER_VERBOSITY > 90:
			if len(path_before) != len(path):
				print("\tbefore pruning: %s" % " < ".join(path_before))
				print("\tafter pruning: %s" % " < ".join(path))

		return path

	def sent(self, ident, ttl, path):
		if ROUTER_VERBOSITY > 60:
			print("%s rt: sent ttl %d ident %s path %s" % \
				(self.callsign, ttl, ident, " < ".join(path)))

		for i in range(0, len(path) - 1):
			self.sent_edges[path[i]][path[i + 1]] = True

	def handle_pkt(self, radio_rssi, pkt):
		# Handle mesh formation packet

		if pkt.to != "QM" or pkt.fr0m != "QM":
			return False

		msg = pkt.msg.upper().strip()
		if not msg:
			if ROUTER_VERBOSITY > 40:
				print("%s: Bad QM packet msg", self.callsign)
			return True

		# Parse message into a path
		path = msg.split("<")
		if ROUTER_VERBOSITY > 50:
			print("%s: rt recv path %s ttl %d ident %s" % \
				(self.callsign, "<".join(path), pkt.ttl, pkt.ident))

		self.learn(pkt.ident, pkt.ttl, path, radio_rssi)

		# Hop count control
		pkt = pkt.decrement_ttl()
		if pkt.ttl < -self.helper['max_ttl']():
			if ROUTER_VERBOSITY > 60:
				print("\tnot forwarding - ttl")
			return True

		# Only add ourselves to path if len(path) <= TTL
		if pkt.ttl >= 0:
			path = [ self.callsign ] + path

		# Prune parts of the route we've already broadcasted
		# but guarantee that path[0] = us when ttl >= 0
		path = self.prune(pkt.ttl >= 0, path)
		if len(path) < 2:
			if ROUTER_VERBOSITY > 90:
				print("\tnothing left after pruning")
			return True

		# Forward with updated path
		pkt = pkt.replace_msg("<".join(path))
		self.helper['sendmsg'](pkt)
		self.sent(pkt.ident, pkt.ttl, path)

		return True

	def get_first_hop(self, to):
		return self.get_next_hop(to, None, self.callsign)

	# Calculate next 'via' station.
	# Returns: "" to resort to diffusion routing
	#          None if packet should not be repeated

	def get_next_hop(self, to, via, fr0m):
		repeater, cost = self._get_next_hop(to, fr0m, (to, ))
		return repeater

	def _get_next_hop(self, to, fr0m, path):
		if to == "QF" or to == "QB" or to == "QM":
			# these always go by diffusion
			return "", 0
		elif to and to[0] == "Q":
			raise Exception("%s rt: asked route to %s" % (self.callsign, to))

		# FIXME cache w/ timeout
		if to == fr0m:
			# should not happen
			raise Exception("%s rt: asked route to itself" % self.callsign)

		recursion = "$" * (len(path) - 1)
		if recursion:
			recursion += " "

		if to in self.cache and fr0m in self.cache[to]:
			via, cost, _ = self.cache[to][fr0m]
			if ROUTER_VERBOSITY > 90:
				print("%s%s rt: using cached %s < %s < %s" % \
					(recursion, self.callsign, to, via, fr0m))
			return via, cost

		if ROUTER_VERBOSITY > 90:
			print("%s%s rt: looking for route %s < %s" % \
				(recursion, self.callsign, to, fr0m))

		if to not in self.edges:
			# Unknown destination
			if CAN_DIFFUSE_UNKNOWN:
				if ROUTER_VERBOSITY > 90:
					print("\tdestination unknown, use diffusion" % to)
				return "", 999999999
			if ROUTER_VERBOSITY > 90:
				print("\tdestination unknown, cannot route" % to)
			return None, 999999999

		if fr0m in self.edges[to]:
			# last hop
			if ROUTER_VERBOSITY > 90:
				print("\tlast hop")
			return to, self.edges[to][fr0m]

		# Try to find cheapest route, backtracking from 'to'
		best_cost = 999999999
		best_via = None
		for penultimate, pcost in self.edges[to].items():
			if ROUTER_VERBOSITY > 90:
				print("\tlooking for route to %s" % penultimate)

			if penultimate in path:
				# would create a loop
				if ROUTER_VERBOSITY > 90:
					print("\t\tloop %s" % str(path))
				continue

			via, cost = self._get_next_hop(penultimate, fr0m, (penultimate,) + path)
			if not via:
				print("\t\tno route")
				continue

			if ROUTER_VERBOSITY > 90:
				print("\t\tcandidate %s < %s < %s cost %d" % (to, via, fr0m, cost))

			# add cost of hast hop
			cost += pcost
			if not best_via or cost < best_cost:
				best_via = via
				best_cost = cost

		if not best_via:
			# Did not find route
			if CAN_DIFFUSE_NOROUTE:
				if ROUTER_VERBOSITY > 90:
					print("\troute not found, using diffusion")
				return "", 999999999
			if ROUTER_VERBOSITY > 90:
				print("\troute not found, giving up")
			return None, 999999999

		if ROUTER_VERBOSITY > 90:
			print("\tadopted %s < %s < %s cost %d" % (to, via, fr0m, best_cost))

		if best_via:
			if to not in self.cache:
				self.cache[to] = {}
			if fr0m not in self.cache[to]:	
				self.cache[to][fr0m] = (best_via, cost, time.time())
				if ROUTER_VERBOSITY > 90:
					print("%s rt: caching %s < %s < %s cost %d" % \
						(self.callsign, to, best_via, fr0m, cost))

		return best_via, best_cost + 1000


loop = asyncio.get_event_loop()

class MeshFormation:
	def __init__(self, station, helper):
		async def probe():
			await asyncio.sleep(1 + random.random() * 5)
			while True:
				pkt = Packet("QM", "", "QM", helper['max_ttl'](), station)
				helper['sendmsg'](pkt)
				await asyncio.sleep(120 + random.random() * 60)
		loop.create_task(probe())
