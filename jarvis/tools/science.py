# -*- coding: utf-8 -*-
"""Science sandbox: symbolic math/physics calculations and chemistry lookups (PubChem).
A simulation & reference sandbox — not a lab. Safety notes are always included."""
import math
import asyncio
import httpx
from . import tool

SAFETY = ("\nSAFETY: This is a calculation/reference result. Any physical build must use rated components, "
          "eye protection, and comply with local law; never build weapons, explosives or toxic syntheses.")


@tool("calculate", "Evaluate or solve math/physics expressions symbolically (SymPy syntax). Examples: 'solve(x**2-4, x)', 'integrate(sin(x), x)', 'sqrt(2*9.81*10)', 'diff(x**3, x)'.",
      {"expression": "string"}, agent="Research Agent")
def calculate(args, ctx):
    try:
        import sympy as sp
        from sympy.parsing.sympy_parser import parse_expr, standard_transformations, implicit_multiplication_application
        expr = args.get("expression", "")
        ns = {k: getattr(sp, k) for k in dir(sp) if not k.startswith("_")}
        ns.update({c: sp.Symbol(c) for c in "xyztuvabcdmnkr"})
        if any(expr.strip().startswith(f) for f in ("solve", "integrate", "diff", "limit", "simplify", "expand", "factor", "series", "Matrix", "dsolve", "nsolve")):
            res = eval(expr, {"__builtins__": {}}, ns)
        else:
            res = parse_expr(expr, local_dict=ns, transformations=standard_transformations + (implicit_multiplication_application,))
        try:
            num = sp.N(res, 8)
        except Exception:
            num = res
        return f"{expr} = {res}" + (f"  ≈ {num}" if str(num) != str(res) else "")
    except Exception as e:
        return f"Could not evaluate: {e}"


@tool("physics", "Physics calculators: projectile (v0 m/s, angle deg, h0 m), energy (mass kg, velocity m/s, height m), spring (k N/m, x m), orbit (mass_central kg, radius m), pressure_force (pressure Pa, area m2), drag (rho, v, Cd, A).",
      {"scenario": "projectile|energy|spring|orbit|pressure_force|drag", "params": "{...numbers}"}, agent="Research Agent")
def physics(args, ctx):
    g, G = 9.80665, 6.674e-11
    sc = args.get("scenario", "")
    p = {k: float(v) for k, v in (args.get("params") or {}).items() if str(v).replace('.', '', 1).replace('-', '', 1).replace('e', '', 1).isdigit() or isinstance(v, (int, float))}
    try:
        if sc == "projectile":
            v, a, h = p.get("v0", 10), math.radians(p.get("angle", 45)), p.get("h0", 0)
            vx, vy = v * math.cos(a), v * math.sin(a)
            t = (vy + math.sqrt(vy ** 2 + 2 * g * h)) / g
            return f"Flight time {t:.2f} s, range {vx * t:.2f} m, max height {h + vy ** 2 / (2 * g):.2f} m (no drag)." + SAFETY
        if sc == "energy":
            m, v, h = p.get("mass", 1), p.get("velocity", 0), p.get("height", 0)
            return f"Kinetic {0.5 * m * v ** 2:.2f} J, potential {m * g * h:.2f} J, momentum {m * v:.2f} kg·m/s." + SAFETY
        if sc == "spring":
            k, x = p.get("k", 100), p.get("x", 0.1)
            return f"Force {k * x:.2f} N, stored energy {0.5 * k * x ** 2:.3f} J; launch speed of mass m: v = sqrt(k/m)·x." + SAFETY
        if sc == "orbit":
            M, r = p.get("mass_central", 5.972e24), p.get("radius", 6.771e6)
            v = math.sqrt(G * M / r)
            return f"Orbital speed {v:.1f} m/s, period {2 * math.pi * r / v / 60:.1f} min, escape speed {v * math.sqrt(2):.1f} m/s."
        if sc == "pressure_force":
            P, A = p.get("pressure", 101325), p.get("area", 0.01)
            return f"Force {P * A:.2f} N ({P * A / 9.80665:.2f} kgf)." + SAFETY
        if sc == "drag":
            rho, v, cd, A = p.get("rho", 1.225), p.get("v", 10), p.get("Cd", 0.47), p.get("A", 0.01)
            return f"Drag force {0.5 * rho * v ** 2 * cd * A:.3f} N."
        return "Unknown scenario. Use: projectile, energy, spring, orbit, pressure_force, drag."
    except Exception as e:
        return f"Physics calc failed: {e}"


@tool("chemistry_lookup", "Look up a chemical compound (by common name) in PubChem: formula, molecular weight, IUPAC name, and GHS hazard summary.",
      {"name": "compound name, e.g. 'acetone', 'sodium bicarbonate'"}, agent="Research Agent")
async def chemistry_lookup(args, ctx):
    name = args.get("name", "").strip()
    base = "https://pubchem.ncbi.nlm.nih.gov/rest/pug"
    try:
        async with httpx.AsyncClient(timeout=15, headers={"User-Agent": "JARVIS/3.0 (science sandbox)"}) as c:
            r = await c.get(f"{base}/compound/name/{name}/property/MolecularFormula,MolecularWeight,IUPACName/JSON")
            if r.status_code != 200:
                w = await c.get("https://en.wikipedia.org/api/rest_v1/page/summary/" + name.replace(" ", "_"))
                if w.status_code == 200:
                    return f"PubChem unavailable ({r.status_code}); Wikipedia summary for {name}: {w.json().get('extract', '')[:800]}" + SAFETY
                return f"No PubChem entry for '{name}' (HTTP {r.status_code})."
            props = r.json()["PropertyTable"]["Properties"][0]
            cid = props["CID"]
            hazards = "n/a"
            try:
                h = await c.get(f"https://pubchem.ncbi.nlm.nih.gov/rest/pug_view/data/compound/{cid}/JSON?heading=GHS+Classification")
                txt = h.text
                import re
                codes = sorted(set(re.findall(r"H\d{3}[^\"]{0,60}", txt)))[:8]
                hazards = "; ".join(codes) if codes else "no GHS hazard statements listed"
            except Exception:
                pass
        return (f"{name}: formula {props.get('MolecularFormula')}, MW {props.get('MolecularWeight')} g/mol, IUPAC {props.get('IUPACName')}, PubChem CID {cid}. "
                f"GHS hazards: {hazards}." + SAFETY)
    except Exception as e:
        return f"Chemistry lookup failed: {e}"
