#!/usr/bin/env python3

# LoRaMaDoR (LoRa-based mesh network for hams) project
# Mesh network simulator / routing algorithms testbed
# Copyright (c) 2019 PU5EPX

import random, asyncio, sys

L2_VERBOSITY=50

loop = asyncio.get_event_loop()

class Radio:
	pkts_transmitted = 0
	bits_transmitted = 0
	runtime = 0

	def __init__(self):
		self.edges = {}
		self.stations = {}
		async def transmitted():
			while True:
				await asyncio.sleep(30)
				Radio.runtime += 30
				print("##### radio: sent %d pkts %d bits %d bps" % 
					(Radio.pkts_transmitted, Radio.bits_transmitted,
					Radio.bits_transmitted / Radio.runtime))
		loop.create_task(transmitted())

	def active_edges(self):
		n = 0
		for _, v in self.edges.items():
			for __, rssi in v.items():
				if rssi is not None:
					n += 1
		return n

	def edge(self, to, fr0m, rssi):
		if fr0m not in self.edges:
			self.edges[fr0m] = {}
		self.edges[fr0m][to] = rssi

	def biedge(self, to, fr0m, rssi1, rssi2):
		self.edge(to, fr0m, rssi1)
		self.edge(fr0m, to, rssi2)

	def attach(self, callsign, station):
		self.stations[callsign] = station

	def send(self, fr0m, pkt):
		Radio.pkts_transmitted += 1
		# 13 is LoRa preamble
		Radio.bits_transmitted += 8 * (3 + len(pkt))

		if fr0m not in self.edges or not self.edges[fr0m]:
			print("radio %s: nobody listens to me", fr0m)
			return

		for dest, rssi in self.edges[fr0m].items():
			if rssi is None:
				if L2_VERBOSITY > 80:
					print("radio %s: not bcasting to %s" % \
						(fr0m, dest))
				continue
			else:
				if L2_VERBOSITY > 70:
					print("radio %s: bcasting %s ident %s" % \
						(fr0m, dest, pkt.ident))

			async def asend(d, r, p):
				await asyncio.sleep(0.1 + random.random())
				self.stations[d].radio_recv(r, p)

			loop.create_task(asend(dest, rssi, pkt))
