/*
  This file is part of Ingen.
  Copyright 2012-2016 David Robillard <http://drobilla.net/>
  JSON output: Poly Effects; portable rewrite for the Beebo desktop build.

  Ingen is free software: you can redistribute it and/or modify it under the
  terms of the GNU Affero General Public License as published by the Free
  Software Foundation, either version 3 of the License, or any later version.

  Ingen is distributed in the hope that it will be useful, but WITHOUT ANY
  WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR
  A PARTICULAR PURPOSE.  See the GNU Affero General Public License for details.

  You should have received a copy of the GNU Affero General Public License
  along with Ingen.  If not, see <http://www.gnu.org/licenses/>.
*/

// The Beebo / Hector UI (digit_ui) talks to Ingen over a socket and expects
// every message as JSON instead of Turtle. On the pedal this came from a
// private serd extension (SERD_JSONTURTLE). This version builds the same
// shape directly from sratom's statements, so it works with stock serd:
//
//   "m12": { "a": ["patch:Put"],
//            "patch:subject": ["ingen:/main/delay1"],
//            "patch:body": { "a": ["ingen:Block"], "ingen:canvasX": ["20.0"] } }
//
// - each message is one "key": {object}; SocketWriter wraps bundles in {}
// - predicates and URIs are shortened to prefix:name where a prefix is known,
//   rdf:type is written as "a"
// - every value is a list of strings, except a single anonymous node
//   ([ ... ]), which is written as a nested object
// - file: URIs are written as plain paths

#include <ingen/JsonWriter.hpp>

#include <ingen/AtomWriter.hpp>
#include <ingen/URI.hpp>
#include <ingen/URIMap.hpp>
#include <ingen/ingen.h>
#include <lv2/atom/atom.h>
#include <serd/serd.h>
#include <sratom/sratom.h>

#include <cstdio>
#include <map>
#include <set>
#include <string>
#include <utility>
#include <vector>

#define USTR(s) reinterpret_cast<const uint8_t*>(s)

namespace ingen {

namespace {

struct JValue {
	bool        is_node;
	std::string str; // literal text, or node id when is_node
};

struct JNode {
	std::vector<std::pair<std::string, std::vector<JValue>>> props;

	std::vector<JValue>& operator[](const std::string& key)
	{
		for (auto& p : props) {
			if (p.first == key) {
				return p.second;
			}
		}
		props.emplace_back(key, std::vector<JValue>{});
		return props.back().second;
	}
};

const char* const k_rdf_type =
    "http://www.w3.org/1999/02/22-rdf-syntax-ns#type";

std::string
node_string(const SerdNode* n)
{
	return (n && n->buf) ? std::string(reinterpret_cast<const char*>(n->buf),
	                                   n->n_bytes)
	                     : std::string{};
}

void
json_escape(std::string& out, const std::string& s)
{
	out += '"';
	for (const char c : s) {
		switch (c) {
		case '"': out += "\\\""; break;
		case '\\': out += "\\\\"; break;
		case '\n': out += "\\n"; break;
		case '\r': out += "\\r"; break;
		case '\t': out += "\\t"; break;
		case '\b': out += "\\b"; break;
		case '\f': out += "\\f"; break;
		default:
			if (static_cast<unsigned char>(c) < 0x20) {
				char buf[8];
				snprintf(buf, sizeof(buf), "\\u%04x", static_cast<unsigned>(c));
				out += buf;
			} else {
				out += c;
			}
		}
	}
	out += '"';
}

} // namespace

struct JsonState {
	SerdEnv*                     env{nullptr};
	std::map<std::string, JNode> nodes;
	std::vector<std::string>     roots;
	std::set<std::string>        nested;
	unsigned long long           counter{0};

	void clear()
	{
		nodes.clear();
		roots.clear();
		nested.clear();
	}

	std::string shorten(const SerdNode* n) const
	{
		const std::string s = node_string(n);
		if (s == k_rdf_type) {
			return "a";
		}
		if (s.rfind("file://", 0) == 0) {
			return s.substr(7);
		}
		SerdNode  prefix = SERD_NODE_NULL;
		SerdChunk suffix{nullptr, 0};
		if (serd_env_qualify(env, n, &prefix, &suffix) && suffix.len > 0) {
			return std::string(reinterpret_cast<const char*>(prefix.buf),
			                   prefix.n_bytes) +
			       ":" +
			       std::string(reinterpret_cast<const char*>(suffix.buf),
			                   suffix.len);
		}
		return s;
	}

	static std::string id(const SerdNode* n)
	{
		return (n->type == SERD_BLANK ? "_:" : "") + node_string(n);
	}

	void statement(const SerdNode* subject,
	               const SerdNode* predicate,
	               const SerdNode* object)
	{
		const std::string sid = id(subject);
		if (!nodes.count(sid)) {
			nodes[sid];
			roots.push_back(sid);
		}

		JValue v{false, {}};
		if (object->type == SERD_BLANK) {
			v.is_node = true;
			v.str     = id(object);
			nested.insert(v.str);
			nodes[v.str];
		} else if (object->type == SERD_URI || object->type == SERD_CURIE) {
			v.str = shorten(object);
		} else {
			v.str = node_string(object);
		}

		nodes[sid][shorten(predicate)].push_back(v);
	}

	void write_node(std::string&           out,
	                const std::string&     nid,
	                std::set<std::string>& seen) const
	{
		const auto it = nodes.find(nid);
		if (it == nodes.end() || seen.count(nid)) {
			json_escape(out, nid);
			return;
		}
		seen.insert(nid);
		out += '{';
		bool first_prop = true;
		for (const auto& p : it->second.props) {
			if (!first_prop) {
				out += ',';
			}
			first_prop = false;
			json_escape(out, p.first);
			out += ':';
			// A single anonymous object is written as the object itself,
			// matching body = m["patch:body"]; body[...] in the UI.
			if (p.second.size() == 1 && p.second[0].is_node) {
				write_node(out, p.second[0].str, seen);
				continue;
			}
			out += '[';
			bool first_v = true;
			for (const auto& v : p.second) {
				if (!first_v) {
					out += ',';
				}
				first_v = false;
				if (v.is_node) {
					write_node(out, v.str, seen);
				} else {
					json_escape(out, v.str);
				}
			}
			out += ']';
		}
		out += '}';
		seen.erase(nid);
	}

	std::string serialise()
	{
		std::string out;
		bool        first = true;
		for (const auto& r : roots) {
			if (nested.count(r)) {
				continue;
			}
			if (!first) {
				out += ',';
			}
			first = false;
			json_escape(out, "m" + std::to_string(++counter));
			out += ':';
			std::set<std::string> seen;
			write_node(out, r, seen);
		}
		return out;
	}
};

static SerdStatus
json_statement(void* handle,
               SerdStatementFlags,
               const SerdNode*,
               const SerdNode* subject,
               const SerdNode* predicate,
               const SerdNode* object,
               const SerdNode*,
               const SerdNode*)
{
	static_cast<JsonState*>(handle)->statement(subject, predicate, object);
	return SERD_SUCCESS;
}

static SerdStatus
json_end(void*, const SerdNode*)
{
	return SERD_SUCCESS;
}

JsonWriter::JsonWriter(URIMap& map, URIs& uris, URI uri)
	: AtomWriter{map, uris, *this}
	, _map{map}
	, _sratom{sratom_new(&map.urid_map())}
	, _base{serd_node_from_string(SERD_URI, USTR("ingen:/"))}
	, _env{serd_env_new(&_base)}
	, _writer{nullptr}
	, _uri{std::move(uri)}
	, _json{new JsonState}
{
	// Use <ingen:/> as base URI, so relative URIs are like bundle paths
	serd_uri_parse(USTR("ingen:/"), &_base_uri);

	serd_env_set_prefix_from_strings(_env, USTR("atom"),  USTR("http://lv2plug.in/ns/ext/atom#"));
	serd_env_set_prefix_from_strings(_env, USTR("doap"),  USTR("http://usefulinc.com/ns/doap#"));
	serd_env_set_prefix_from_strings(_env, USTR("ingen"), USTR(INGEN_NS));
	serd_env_set_prefix_from_strings(_env, USTR("lv2"),   USTR("http://lv2plug.in/ns/lv2core#"));
	serd_env_set_prefix_from_strings(_env, USTR("midi"),  USTR("http://lv2plug.in/ns/ext/midi#"));
	serd_env_set_prefix_from_strings(_env, USTR("owl"),   USTR("http://www.w3.org/2002/07/owl#"));
	serd_env_set_prefix_from_strings(_env, USTR("patch"), USTR("http://lv2plug.in/ns/ext/patch#"));
	serd_env_set_prefix_from_strings(_env, USTR("rdf"),   USTR("http://www.w3.org/1999/02/22-rdf-syntax-ns#"));
	serd_env_set_prefix_from_strings(_env, USTR("rdfs"),  USTR("http://www.w3.org/2000/01/rdf-schema#"));
	serd_env_set_prefix_from_strings(_env, USTR("xsd"),   USTR("http://www.w3.org/2001/XMLSchema#"));

	_json->env = _env;
	sratom_set_sink(_sratom,
	                reinterpret_cast<const char*>(_base.buf),
	                json_statement,
	                json_end,
	                _json);
}

JsonWriter::~JsonWriter()
{
	sratom_free(_sratom);
	serd_env_free(_env);
	delete _json;
}

bool
JsonWriter::write(const LV2_Atom* msg, int32_t)
{
	_json->clear();
	sratom_write(_sratom, &_map.urid_unmap(), 0,
	             nullptr, nullptr, msg->type, msg->size, LV2_ATOM_BODY_CONST(msg));
	const std::string text = _json->serialise();
	if (!text.empty()) {
		text_sink(text.data(), text.size());
	}
	_json->clear();
	return true;
}

} // namespace ingen
