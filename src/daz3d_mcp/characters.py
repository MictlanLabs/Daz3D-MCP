"""Character sheets: a reusable, editable description of a character and how it maps to the dials
installed on each Genesis generation."""

from __future__ import annotations

import hashlib
import json
import re
import time
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from daz3d_mcp.paths import config_dir

SHEET_FORMAT = "daz3d-mcp-character"
SHEET_VERSION = 1

Role = Literal["figure", "mouth", "eyes"]
ROLES: tuple[Role, ...] = ("figure", "mouth", "eyes")
Direction = Literal["both", "up", "down"]

BASE_FIGURES = {
    "Genesis 9": "People/Genesis 9/Genesis 9.duf",
    "Genesis 8.1 Female": "People/Genesis 8 Female/Genesis 8.1 Basic Female.duf",
    "Genesis 8.1 Male": "People/Genesis 8 Male/Genesis 8.1 Basic Male.duf",
    "Genesis 8 Female": "People/Genesis 8 Female/Genesis 8 Basic Female.duf",
    "Genesis 8 Male": "People/Genesis 8 Male/Genesis 8 Basic Male.duf",
}

FILLER = {"body", "full", "size", "proportion", "fbm", "pbm", "phm", "ctrl", "bs", "scale", "mcp"}
EXCLUDED_TOKENS = {"asymmetry", "left", "right", "l", "r", "toon", "fix", "adjust", "adjustment", "legacy", "hd",
                   "nipple", "nipples", "eyelashes", "eyelash", "lashes", "navel", "cameltoe", "genitalia",
                   "propagating", "anime", "expression", "pose"}
EXCLUDED_GROUPS = re.compile(r"/(Pose Controls|People|Characters|Tools|Hidden)(/|$)", re.IGNORECASE)
NOT_SKIN = re.compile(r"eye|iris|pupil|sclera|cornea|lacrimal|tear|moisture|teeth|mouth|tongue|gum|lash|nail|brow",
                      re.IGNORECASE)

MISSING_HINT = ("Dials that are not installed cannot be set. More shape dials come with Daz's base morph packs "
                "(Genesis 9 Head and Body Morphs; Genesis 8 / 8.1 Female or Male Head and Body Morphs). "
                "Meanwhile, morph_generate(figure) makes 20 of them (nose, chin, jaw, cheeks, ears, age, weight, muscle...) on Genesis 9 and 8 / 8.1, "
                "and mixing the installed character heads and bodies at partial values in `dials` "
                "(morph_list(figure, query=\"people\")) also gives a unique face and body.")


@dataclass(frozen=True)
class Option:
    dials: tuple[str, ...]
    role: Role = "figure"
    direction: Direction = "both"
    gain: float = 1.0
    approx: bool = False
    gains: tuple[float, ...] = ()


@dataclass(frozen=True)
class Search:
    words: frozenset[str]
    direction: Direction = "both"
    gain: float = 1.0


@dataclass(frozen=True)
class Trait:
    name: str
    category: Literal["body", "face"]
    plus: str
    minus: str
    primary: tuple[Option, ...] = ()
    search: tuple[Search, ...] = ()
    fallback: tuple[Option, ...] = ()
    scale_gain: float | None = None
    low: float = -1.0
    inherent: str | None = None


def _norm(token: str) -> str:
    if len(token) > 3 and token.endswith("s") and not token.endswith("ss"):
        return token[:-1]
    return token


def tokens(label: str) -> set[str]:
    return {_norm(t) for t in re.findall(r"[a-z0-9]+", label.lower())}


def _s(words: str, direction: Direction = "both", gain: float = 1.0) -> Search:
    return Search(frozenset(_norm(w) for w in words.split()), direction, gain)


def _pair(part: str, gain: float = 1.0) -> Option:
    return Option((f"Asymmetry {part} Left", f"Asymmetry {part} Right"), gain=gain)


def _one(*labels: str, role: Role = "figure", direction: Direction = "both", gain: float = 1.0,
         approx: bool = False) -> Option:
    return Option(tuple(labels), role, direction, gain, approx)


def _t(name: str, category: Literal["body", "face"], plus: str, minus: str, **kw) -> Trait:
    return Trait(name, category, plus, minus, **kw)


PROPORTION = 0.3

TRAITS: dict[str, Trait] = {t.name: t for t in [
    _t("feminine", "body", "feminine body and face (Genesis 9 base shape)", "-", low=0.0, inherent="Female",
       primary=(_one("Base Feminine", direction="up"),)),
    _t("masculine", "body", "masculine body and face (Genesis 9 base shape)", "-", low=0.0, inherent="Male",
       primary=(_one("Base Masculine", direction="up"),)),
    _t("height", "body", "taller", "shorter", primary=(_one("Proportion Height", gain=PROPORTION),),
       search=(_s("height", gain=PROPORTION),), scale_gain=0.07),
    _t("weight", "body", "heavier, fuller body", "thinner",
       search=(_s("heavy", "up"), _s("weight"), _s("fat", "up"), _s("plump", "up"), _s("voluptuous", "up", 0.6),
               _s("thin", "down"), _s("slim", "down"), _s("skinny", "down"), _s("emaciated", "down", 0.6))),
    _t("muscle", "body", "more muscular, athletic", "softer, less defined",
       search=(_s("bodybuilder", "up", 0.6), _s("muscular", "up"), _s("muscle", "up"), _s("tone", "up"),
               _s("fitness", "up"), _s("fitness detail", "up"), _s("bodybuilder detail", "up", 0.6))),
    _t("age", "body", "older (aged face and body)", "younger, more youthful",
       search=(_s("age"), _s("aged", "up"), _s("old", "up"), _s("older", "up"), _s("elderly", "up"),
               _s("aging", "up"), _s("young", "down"), _s("younger", "down"), _s("youthful", "down"))),
    _t("bust", "body", "larger breasts or chest", "smaller",
       search=(_s("breast"), _s("bust"), _s("breast volume"), _s("pectoral")),
       fallback=(_one("Proportion Chest Size", gain=0.4, approx=True), _one("Chest Scale", gain=0.3, approx=True))),
    _t("chest_width", "body", "wider chest and ribcage", "narrower",
       primary=(_one("Proportion Chest Width", gain=PROPORTION),), search=(_s("chest width"),)),
    _t("shoulders", "body", "broader shoulders", "narrower",
       primary=(_one("Proportion Shoulder Width", gain=PROPORTION),),
       search=(_s("shoulder width"), _s("shoulder"))),
    _t("waist", "body", "wider waist", "narrower waist", search=(_s("waist width"), _s("waist"))),
    _t("hips", "body", "wider hips", "narrower hips",
       search=(_s("hip"), _s("hip width"), _s("pear figure", "up", 0.6))),
    _t("glutes", "body", "larger glutes", "smaller", search=(_s("glute"), _s("buttock"))),
    _t("legs_length", "body", "longer legs", "shorter legs",
       primary=(_one("Proportion Legs Length", gain=PROPORTION),), search=(_s("leg length"),)),
    _t("arms_length", "body", "longer arms", "shorter arms",
       primary=(_one("Proportion Arms Length", gain=PROPORTION),), search=(_s("arm length"),)),
    _t("torso_length", "body", "longer torso", "shorter torso",
       primary=(_one("Proportion Torso Length", gain=PROPORTION),), search=(_s("torso length"),)),
    _t("neck_length", "body", "longer neck", "shorter neck",
       primary=(_one("Proportion Neck Length", gain=PROPORTION),), search=(_s("neck length"),)),
    _t("neck_width", "body", "thicker neck", "thinner neck", search=(_s("neck width"), _s("neck thickness"))),
    _t("head_size", "body", "bigger head", "smaller head",
       primary=(_one("Proportion Head Size", gain=PROPORTION),), search=(_s("head"),),
       fallback=(_one("Head Propagating Scale", gain=0.15, approx=True),)),
    _t("hands_size", "body", "bigger hands", "smaller hands",
       primary=(_one("Proportion Hand Size", gain=PROPORTION),), search=(_s("hand"),),
       fallback=(_one("Hand Propagating Scale", gain=0.15, approx=True),)),
    _t("fingers_length", "body", "longer fingers", "shorter fingers",
       primary=(_one("Proportion Fingers Length", gain=PROPORTION),), search=(_s("finger length"),)),
    _t("feet_size", "body", "bigger feet", "smaller feet",
       primary=(_one("Proportion Foot Size", gain=PROPORTION),), search=(_s("foot"), _s("feet")),
       fallback=(_one("Foot Propagating Scale", gain=0.15, approx=True),)),
    _t("nails_length", "body", "longer nails", "shorter nails", search=(_s("nail length"),)),

    _t("face_width", "face", "wider face", "narrower face", search=(_s("face width"), _s("face wide"))),
    _t("face_length", "face", "longer face", "shorter face",
       search=(_s("face length"), _s("face long"), _s("face height"))),
    _t("face_round", "face", "rounder, softer face", "less round",
       search=(_s("face round"), _s("round face")), fallback=(_pair("Face Round"),)),
    _t("face_square", "face", "squarer face", "less square",
       search=(_s("face square"), _s("square face")), fallback=(_pair("Face Square"),)),
    _t("face_heart", "face", "heart-shaped face (wide temples, narrow chin)", "less heart-shaped",
       search=(_s("face heart"), _s("heart face")), fallback=(_pair("Face Heart"),)),
    _t("forehead_height", "face", "taller forehead", "shorter forehead",
       search=(_s("forehead height"), _s("forehead"))),
    _t("brow_height", "face", "brows sit higher", "brows sit lower",
       search=(_s("brow height"), _s("eyebrow height")), fallback=(_pair("Brow Height"),)),
    _t("brow_ridge", "face", "stronger, more prominent brow ridge", "flatter brow",
       search=(_s("brow ridge"), _s("brow depth"), _s("brow")), fallback=(_pair("Brow Size"),)),
    _t("eyes_size", "face", "bigger eyes", "smaller eyes", search=(_s("eye"), _s("eye scale")),
       fallback=(_one("Eye Whole Size", role="eyes", gain=0.3, approx=True),)),
    _t("eyes_width", "face", "longer, more almond eye opening", "shorter eye opening",
       search=(_s("eye width"),)),
    _t("eyes_height", "face", "rounder, more open eyes", "narrower eye opening",
       search=(_s("eye height"), _s("eye open"))),
    _t("eyes_spacing", "face", "eyes set wider apart", "eyes closer together",
       search=(_s("eye spacing"), _s("eye distance"), _s("eye apart")), fallback=(_pair("Eyes Position Width"),)),
    _t("eyes_position", "face", "eyes higher on the face", "eyes lower",
       search=(_s("eye position height"), _s("eye vertical")), fallback=(_pair("Eyes Position Height"),)),
    _t("eyes_deep", "face", "deep-set eyes", "eyes further forward",
       search=(_s("eye depth"), _s("eye deep")), fallback=(_one("Asymmetry Eyes Position Depth Left",
                                                              "Asymmetry Eyes Position Depth Right", gain=-1.0),)),
    _t("eyes_tilt", "face", "outer corners up (upturned, cat-like)", "outer corners down (downturned)",
       search=(_s("eye angle"), _s("eye tilt"), _s("eye slant")), fallback=(_pair("Eyes Angle"),)),
    _t("eyelids_heavy", "face", "heavier, hooded upper lids", "more open upper lids",
       search=(_s("eyelid hooded"), _s("eye hooded"), _s("eyelid upper height")),
       fallback=(_pair("Eyelids Upper Relax"),)),
    _t("eyelids_lower", "face", "lower lids droop more", "lower lids tighter",
       fallback=(_pair("Eyelids Lower Relax"),)),
    _t("eyelid_crease", "face", "higher eyelid crease", "lower crease (monolid look)",
       search=(_s("eyelid crease"), _s("eye crease")), fallback=(_pair("Eyelids Crease Height"),)),
    _t("iris_size", "face", "bigger irises", "smaller irises",
       primary=(_one("Eye Iris Size Larger", role="eyes", direction="up"),
                _one("Eye Iris Size Smaller", role="eyes", direction="down")),
       search=(_s("iris"),)),
    _t("pupils_slit", "face", "slit, cat-like pupils", "-", low=0.0,
       primary=(_one("Eye Pupil Slit", role="eyes", direction="up"),), search=(_s("pupil slit", "up"),)),
    _t("cheekbones", "face", "higher, more prominent cheekbones", "flatter cheekbones",
       search=(_s("cheekbone"), _s("cheekbone height"), _s("cheekbone prominence"))),
    _t("cheeks_fullness", "face", "fuller cheeks", "hollow cheeks",
       search=(_s("cheek"), _s("cheek fullness"), _s("cheek hollow", "down")), fallback=(_pair("Cheek Size"),)),
    _t("jaw_width", "face", "wider jaw", "narrower jaw", search=(_s("jaw width"), _s("jaw wide"), _s("jaw"))),
    _t("jaw_definition", "face", "sharper, more defined jawline", "softer jawline",
       search=(_s("jaw definition"), _s("jawline definition"))),
    _t("chin_length", "face", "longer chin", "shorter chin", search=(_s("chin height"), _s("chin length"))),
    _t("chin_width", "face", "wider chin", "narrower chin", search=(_s("chin width"),)),
    _t("chin_forward", "face", "chin juts forward", "receding chin",
       search=(_s("chin depth"), _s("chin forward"), _s("chin prominence"))),
    _t("chin_cleft", "face", "cleft chin", "-", low=0.0, search=(_s("chin cleft", "up"), _s("chin crease", "up"))),
    _t("nose_size", "face", "bigger nose", "smaller nose", search=(_s("nose"),)),
    _t("nose_width", "face", "wider nose", "narrower nose", search=(_s("nose width"), _s("nose wide")),
       fallback=(Option(("Asymmetry Nose Wing Size Left", "Asymmetry Nose Wing Size Right"), approx=True),)),
    _t("nose_length", "face", "longer nose", "shorter nose", search=(_s("nose length"), _s("nose long"))),
    _t("nose_bridge", "face", "higher, stronger nose bridge", "flatter bridge",
       search=(_s("nose bridge height"), _s("nose bridge"))),
    _t("nose_hump", "face", "nose with a hump (aquiline)", "-", low=0.0,
       search=(_s("nose hump", "up"), _s("nose bump", "up"), _s("nose aquiline", "up"))),
    _t("nose_tip_up", "face", "upturned nose tip", "downturned tip",
       search=(_s("nose tip height"), _s("nose tip up"), _s("nose tip angle"))),
    _t("nose_tip_size", "face", "rounder, bigger nose tip", "thinner tip",
       search=(_s("nose tip width"), _s("nose tip"), _s("nose tip round"))),
    _t("nostrils_width", "face", "wider nostrils", "narrower nostrils",
       search=(_s("nostril width"), _s("nostril"), _s("nose flare"), _s("nose wing width")),
       fallback=(_pair("Nose Wing Size"),)),
    _t("nostrils_height", "face", "nostrils higher", "nostrils lower",
       search=(_s("nostril height"),), fallback=(_pair("Nose Wing Height Position"),)),
    _t("lips_fullness", "face", "fuller lips", "thinner lips",
       search=(_s("lip"), _s("lip fullness"), _s("lip full"), _s("lip thickness"), _s("lip volume")),
       fallback=(Option(("Asymmetry Lip Upper Thickness Left", "Asymmetry Lip Upper Thickness Right",
                         "Asymmetry Lip Lower Thickness Left", "Asymmetry Lip Lower Thickness Right")),)),
    _t("lip_upper", "face", "fuller upper lip", "thinner upper lip",
       search=(_s("lip upper"), _s("lip upper thickness"), _s("lip upper volume")),
       fallback=(_pair("Lip Upper Thickness"),)),
    _t("lip_lower", "face", "fuller lower lip", "thinner lower lip",
       search=(_s("lip lower"), _s("lip lower thickness"), _s("lip lower volume")),
       fallback=(_pair("Lip Lower Thickness"),)),
    _t("mouth_width", "face", "wider mouth", "narrower mouth", search=(_s("mouth width"), _s("mouth wide"))),
    _t("mouth_corners", "face", "corners of the mouth turn up at rest", "corners turn down",
       search=(_s("mouth corner"), _s("mouth corner height")), fallback=(_pair("Mouth Angle"),)),
    _t("cupid_bow", "face", "lifted middle of the lips (stronger cupid's bow)", "flatter middle",
       search=(_s("cupid bow"), _s("lip peak")), fallback=(_pair("Mouth Mid Curve"),)),
    _t("ears_size", "face", "bigger ears", "smaller ears", search=(_s("ear"),)),
    _t("ears_pointed", "face", "pointed, elf-like ears", "-", low=0.0,
       search=(_s("ear elf long", "up"), _s("ear elf", "up"), _s("elf ear", "up"), _s("ear pointed", "up"),
               _s("ear point", "up"))),
    _t("ears_out", "face", "ears stick out", "ears flat against the head",
       search=(_s("ear out"), _s("ear protrude"), _s("ear angle"))),
    _t("ears_height", "face", "ears sit higher", "ears sit lower",
       search=(_s("ear height"),), fallback=(_pair("Ears Position Height"),)),
    _t("teeth_size", "face", "bigger teeth", "smaller teeth",
       primary=(_one("Teeth Size Upper", "Teeth Size Lower", role="mouth"),), search=(_s("teeth"),)),
    _t("teeth_length", "face", "longer teeth", "shorter teeth",
       primary=(_one("Teeth Length Upper", "Teeth Length Lower", role="mouth"),), search=(_s("teeth length"),)),
    _t("teeth_crooked", "face", "irregular, crooked teeth", "more even teeth",
       primary=(_one("Teeth Irregular", role="mouth"),), search=(_s("teeth irregular"), _s("teeth crooked"))),
    _t("teeth_gap", "face", "gap between the front teeth", "-", low=0.0,
       primary=(_one("Teeth Center Gap Upper", role="mouth", direction="up"),),
       search=(_s("teeth gap", "up"), _s("teeth center gap", "up"))),
    _t("teeth_width", "face", "wider individual teeth", "narrower teeth",
       primary=(_one("Teeth Individual Width", role="mouth"),), search=(_s("teeth width"),)),
    _t("fangs", "face", "fangs (long canines)", "-", low=0.0,
       search=(_s("fang", "up"), _s("vampire fang", "up"), _s("canine", "up"), _s("teeth canine", "up")),
       fallback=(_one("Toon Teeth Canines Upper", direction="up", approx=True),)),
    _t("wrinkles", "face", "wrinkles (aged skin detail)", "-", low=0.0,
       search=(_s("wrinkle", "up"), _s("wrinkles face", "up"), _s("forehead wrinkle", "up"),
               _s("crow feet", "up"))),
    _t("eyelashes_length", "face", "longer eyelashes", "-", low=0.0,
       primary=(_one("Eyelashes Length Uniform Upper", "Eyelashes Length Uniform Lower", direction="up"),)),
    _t("eyelashes_curl", "face", "more curled eyelashes", "straighter lashes",
       primary=(_one("Eyelashes Curl Uniform Upper", "Eyelashes Curl Uniform Lower"),)),
    _t("lashes_volume", "face", "thicker, fuller lashes", "-", low=0.0,
       primary=(_one("Eyelashes Large Uniform Upper", "Eyelashes Large Uniform Lower", direction="up"),)),
    _t("lashes_flare", "face", "outer lashes flare up (winged, cat-eye lashes)", "outer lashes droop",
       primary=(_one("Eyelashes Outer Height Upper"),)),
    _t("lashes_sparse", "face", "fewer lashes (1 = none: alien, burned, ill)", "-", low=0.0,
       primary=(_one("Eyelashes Gone Upper", "Eyelashes Gone Lower", direction="up"),)),
    _t("lashes_natural", "face", "irregular, natural-looking lashes", "-", low=0.0,
       primary=(_one("Eyelashes Length Irregular Upper", "Eyelashes Length Irregular Lower", direction="up",
                     gain=0.5),)),
    _t("eyes_inner_corner", "face", "inner eye corners covered (epicanthic fold)", "open inner corners",
       search=(_s("epicanthic"), _s("epicanthic fold"), _s("eye inner corner"), _s("eye corner inner"))),
    _t("eye_bags", "face", "bags under the eyes", "-", low=0.0,
       search=(_s("eye bag", "up"), _s("under eye", "up"), _s("tear trough", "up"))),
    _t("cornea_bulge", "face", "more domed corneas (livelier eye highlights)", "flatter corneas",
       search=(_s("eye cornea bulge"), _s("cornea bulge"), _s("cornea"))),
    _t("teeth_taper", "face", "tapered, pointier teeth (sharp, predatory)", "squarer, blunter teeth",
       primary=(_one("Teeth Individual Taper", role="mouth"),), search=(_s("teeth taper"), _s("teeth sharp"))),
    _t("gums_hidden", "face", "gumline tucked up, little gum shows", "-", low=0.0,
       primary=(_one("Teeth Tucked Gumline", role="mouth", direction="up"),),
       search=(_s("teeth tucked gumline", "up"), _s("gumline", "up"))),
    _t("bite", "face", "overbite (upper teeth ahead, buck teeth)", "underbite (lower jaw ahead)",
       search=(_s("overbite", "up"), _s("underbite", "down"), _s("bite"))),
    _t("fangs_lower", "face", "lower fangs, tusks", "-", low=0.0,
       search=(_s("tusk", "up"), _s("fang lower", "up"), _s("canine lower", "up")),
       fallback=(_one("Toon Teeth Canines Lower", direction="up", approx=True),)),
    _t("earlobes", "face", "bigger, fleshier earlobes", "small, attached lobes",
       search=(_s("ear lobe"), _s("earlobe"), _s("ear lobe size"))),
    _t("ears_angle", "face", "ears tilted back", "ears more upright",
       search=(_s("ear angle"), _s("ear rotate"), _s("ear rotation"))),
    _t("nose_crooked", "face", "nose bent to the character's left (broken-looking)", "bent to the right",
       search=(_s("nose crooked"), _s("nose broken")),
       fallback=(_one("Asymmetry Nose Bridge Horizontal", "Asymmetry Nose Base Twist", gain=0.5),)),
    _t("nose_projection", "face", "nose tip sticks out further", "flatter nose, closer to the face",
       search=(_s("nose depth"), _s("nose projection"), _s("nose tip depth"))),
    _t("nose_bridge_width", "face", "wider nose bridge", "thinner bridge", search=(_s("nose bridge width"),)),
    _t("septum", "face", "septum hangs below the nostrils", "nostril rims lower",
       search=(_s("nose septum"), _s("columella"), _s("nose septum height"))),
    _t("philtrum", "face", "longer space between nose and lip", "shorter",
       search=(_s("philtrum"), _s("philtrum height"), _s("philtrum length"))),
    _t("lips_protrusion", "face", "lips pushed forward", "lips set back",
       search=(_s("lip depth"), _s("lip protrusion"), _s("lip forward"), _s("mouth depth"))),
    _t("lower_lip_pout", "face", "pouty lower lip", "tucked lower lip",
       search=(_s("lip lower pout"), _s("lip lower depth"), _s("pout"))),
    _t("dimples", "face", "cheek dimples at rest", "-", low=0.0,
       search=(_s("dimple", "up"), _s("cheek dimple", "up"))),
    _t("temples", "face", "fuller temples", "hollow, sunken temples",
       search=(_s("temple"), _s("temple depth"), _s("temple width"))),
    _t("nasolabial", "face", "deeper smile lines (nasolabial folds)", "-", low=0.0,
       search=(_s("nasolabial", "up"), _s("nasolabial fold", "up"), _s("smile line", "up"))),
    _t("cheekbone_width", "face", "wider cheekbones", "narrower cheekbones", search=(_s("cheekbone width"),)),
    _t("jaw_angle", "face", "sharp, high jaw angle", "rounded, low jaw angle",
       search=(_s("jaw angle"), _s("jaw curve"))),
    _t("jaw_shift", "face", "jaw shifted to the character's left", "shifted to the right",
       fallback=(_one("Asymmetry Jaw Horizontal Balance", gain=0.3),)),
    _t("jowls", "face", "sagging lower cheeks (jowls)", "-", low=0.0, search=(_s("jowl", "up"),)),
    _t("double_chin", "face", "double chin, fat under the chin", "-", low=0.0,
       search=(_s("double chin", "up"), _s("chin fat", "up"), _s("neck fat", "up"))),
    _t("forehead_slope", "face", "forehead slopes back", "upright, rounded forehead",
       search=(_s("forehead slope"), _s("forehead angle"), _s("forehead depth"))),
    _t("forehead_width", "face", "wider forehead", "narrower forehead", search=(_s("forehead width"),)),
    _t("skull_back", "face", "longer back of the head", "flatter back of the head",
       search=(_s("cranium"), _s("skull depth"), _s("head depth"), _s("head back"))),
    _t("asymmetry", "face", "natural unevenness between the two sides of the face", "-", low=0.0,
       fallback=(Option(("Asymmetry Brow Height Left", "Asymmetry Eyes Position Height Right",
                         "Asymmetry Mouth Angle Left", "Asymmetry Nose Tip Balance Left",
                         "Asymmetry Jaw Horizontal Balance", "Asymmetry Eyelids Upper Relax Right"),
                        direction="up", gains=(0.12, 0.08, 0.1, 0.1, 0.06, 0.1)),)),
    _t("adams_apple", "body", "prominent Adam's apple", "-", low=0.0,
       search=(_s("adam apple", "up"), _s("adams apple", "up"), _s("larynx", "up"))),
    _t("belly", "body", "round belly", "flat stomach",
       search=(_s("belly"), _s("stomach"), _s("abdomen"), _s("gut", "up"), _s("pregnant", "up", 0.6))),
    _t("thighs", "body", "thicker thighs", "thinner thighs", search=(_s("thigh"), _s("thigh size"))),
    _t("calves", "body", "bigger calves", "thinner calves", search=(_s("calf"), _s("calve"), _s("calf size"))),
    _t("upper_arms", "body", "thicker upper arms, bigger biceps", "thinner arms",
       search=(_s("upper arm"), _s("bicep"), _s("arm"))),
    _t("forearms", "body", "thicker forearms", "thinner forearms", search=(_s("forearm"),)),
    _t("breast_shape", "body", "perkier, higher breasts", "lower, natural hang",
       search=(_s("breast perk"), _s("breast perky", "up"), _s("breast sag", "down"), _s("natural hang", "down"),
               _s("breast gone down", "down"))),
]}


def catalog() -> list[dict]:
    return [{"trait": t.name, "category": t.category, "plus": t.plus, "minus": t.minus,
             "range": [t.low, 1.0]} for t in TRAITS.values()]


def unknown_traits(names: list[str]) -> list[dict]:
    out = []
    for name in names:
        if name in TRAITS:
            continue
        words = set(name.lower().replace("-", "_").split("_"))
        similar = [t for t in TRAITS if words & set(t.split("_"))][:6]
        out.append({"trait": name, "similar": similar})
    return out


@dataclass
class Dial:
    label: str
    name: str
    group: str
    lo: float
    hi: float
    node: str
    role: Role

    @classmethod
    def from_entry(cls, entry: dict, node: str, role: Role) -> Dial:
        return cls(str(entry.get("label", "")), str(entry.get("name", "")), str(entry.get("group", "")),
                   float(entry.get("min", -1.0)), float(entry.get("max", 1.0)), node, role)


@dataclass
class Inventory:
    nodes: dict[Role, str]
    dials: list[Dial]

    def find(self, wanted: str, role: Role) -> Dial | None:
        low = wanted.lower()
        for d in self.dials:
            if d.role == role and (d.label.lower() == low or d.name.lower() == low):
                return d
        return None

    def searchable(self) -> list[tuple[Dial, frozenset[str]]]:
        out = []
        for d in self.dials:
            if d.role != "figure" or EXCLUDED_GROUPS.search(d.group):
                continue
            toks = tokens(d.label)
            if toks & EXCLUDED_TOKENS:
                continue
            out.append((d, frozenset(toks - FILLER)))
        return out


@dataclass
class Resolution:
    values: dict[str, dict[str, float]] = field(default_factory=dict)
    traits: dict[str, dict] = field(default_factory=dict)
    missing: list[dict] = field(default_factory=list)
    scale_factor: float = 1.0

    def add(self, dial: Dial, value: float) -> float:
        node = self.values.setdefault(dial.node, {})
        node[dial.label] = round(max(dial.lo, min(dial.hi, node.get(dial.label, 0.0) + value)), 4)
        return node[dial.label]


def _wants(direction: Direction, value: float, dial_lo: float) -> bool:
    if direction == "up":
        return value > 0
    if direction == "down":
        return value < 0
    return value >= 0 or dial_lo < 0


def _amount(direction: Direction, value: float, gain: float) -> float:
    return abs(value) * gain if direction in ("up", "down") else value * gain


def _try_option(inv: Inventory, opt: Option, value: float) -> list[tuple[Dial, float]] | None:
    found = [inv.find(label, opt.role) for label in opt.dials]
    if any(d is None for d in found):
        return None
    if not all(_wants(opt.direction, value, d.lo) for d in found if d):
        return None
    gains = opt.gains or tuple(opt.gain for _ in found)
    amounts = [_amount(opt.direction, value, g) for g in gains]
    if any(a < 0 and d.lo >= 0 for d, a in zip(found, amounts) if d):
        return None
    return [(d, a) for d, a in zip(found, amounts) if d]


def _try_search(searchable: list[tuple[Dial, frozenset[str]]], s: Search, value: float) -> tuple[Dial, float] | None:
    hits = [d for d, toks in searchable if toks == s.words and _wants(s.direction, value, d.lo)]
    if not hits:
        return None
    hits.sort(key=lambda d: (len(d.label), d.label))
    return hits[0], _amount(s.direction, value, s.gain)


def is_generated(dial: Dial) -> bool:
    return "daz3d-mcp" in dial.group.lower()


def _is_pair(labels: tuple[str, ...]) -> bool:
    sides = {re.sub(r" (Left|Right)$", "", label) for label in labels}
    ends = all(label.endswith((" Left", " Right")) for label in labels)
    return ends and len(labels) == 2 * len(sides)


def resolve(traits: dict[str, float], inv: Inventory, generation: str | None) -> Resolution:
    res = Resolution()
    everything = inv.searchable()
    searchable = [(d, t) for d, t in everything if not is_generated(d)]
    generated = [(d, t) for d, t in everything if is_generated(d)]
    for name, value in traits.items():
        trait = TRAITS.get(name)
        if trait is None or abs(value) < 1e-9:
            continue
        picked: list[tuple[Dial, float]] | None = None
        how = ""
        approx = False
        for opt in trait.primary:
            picked = _try_option(inv, opt, value)
            if picked:
                how, approx = "dial", opt.approx
                break
        if not picked:
            for s in trait.search:
                hit = _try_search(searchable, s, value)
                if hit:
                    picked, how = [hit], "found"
                    break
        if not picked:
            for opt in trait.fallback:
                if opt.approx:
                    continue
                picked = _try_option(inv, opt, value)
                if picked:
                    how = "pair" if _is_pair(opt.dials) else "dial"
                    break
        if not picked:
            for s in trait.search:
                hit = _try_search(generated, s, value)
                if hit:
                    picked, how = [hit], "generated"
                    break
        if not picked:
            for opt in trait.fallback:
                if not opt.approx:
                    continue
                picked = _try_option(inv, opt, value)
                if picked:
                    how, approx = "dial", True
                    break
        if picked:
            entry: dict = {"value": value, "how": how, "dials": {}}
            for dial, amount in picked:
                entry["dials"].setdefault(dial.node, {})[dial.label] = res.add(dial, amount)
            if approx:
                entry["approximated"] = True
            res.traits[name] = entry
            continue
        if trait.inherent and generation and trait.inherent in generation and value > 0:
            res.traits[name] = {"value": value, "how": "base figure", "dials": {}}
            continue
        if trait.scale_gain is not None:
            res.scale_factor *= 1 + value * trait.scale_gain
            res.traits[name] = {"value": value, "how": "scale", "scale": round(1 + value * trait.scale_gain, 4),
                                "approximated": True}
            continue
        reason = "no installed dial" if value >= trait.low else "this trait only goes one way (0 to 1)"
        res.missing.append({"trait": name, "value": value, "reason": reason})
    return res


def inventory_from(listings: dict[Role, tuple[str, list[dict]]]) -> Inventory:
    dials: list[Dial] = []
    nodes: dict[Role, str] = {}
    for role, (node, entries) in listings.items():
        nodes[role] = node
        dials += [Dial.from_entry(e, node, role) for e in entries]
    return Inventory(nodes, dials)


def follower_roles(wearing: list[dict]) -> dict[Role, str]:
    roles: dict[Role, str] = {}
    for item in wearing:
        label = str(item.get("label", ""))
        base = re.sub(r"\s*\(\d+\)$", "", label)
        if re.search(r"\bMouth$", base) and "mouth" not in roles:
            roles["mouth"] = label
        elif re.search(r"\bEyes$", base) and "eyes" not in roles:
            roles["eyes"] = label
    return roles


def skin_surfaces(surfaces: list[str]) -> list[str]:
    return [s for s in surfaces if not NOT_SKIN.search(s)]


def zeroed(previous: dict[str, dict[str, float]], current: dict[str, dict[str, float]]) -> dict[str, dict[str, float]]:
    out: dict[str, dict[str, float]] = {}
    for node, dials in previous.items():
        for label in dials:
            if label not in current.get(node, {}):
                out.setdefault(node, {})[label] = 0.0
    return out


def slug(name: str) -> str:
    text = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-").lower()
    return text or "character"


def characters_dir(configured: str | None) -> Path:
    return Path(configured).expanduser() if configured else config_dir() / "characters"


def sheet_path(folder: Path, name_or_path: str) -> Path:
    p = Path(name_or_path).expanduser()
    if p.suffix.lower() == ".json" and p.is_absolute():
        return p
    return folder / f"{slug(name_or_path)}.json"


def now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def new_sheet(name: str) -> dict:
    return {
        "format": SHEET_FORMAT,
        "version": SHEET_VERSION,
        "name": name,
        "description": None,
        "notes": None,
        "figure": {"generation": None, "base": None, "character": None},
        "body": {},
        "face": {},
        "height_cm": None,
        "dials": {},
        "skin": {"preset": None, "tone": None, "details": None},
        "eyes": {"color": None, "iris": None, "preset": None, "left": None, "right": None, "sclera": None},
        "hair": {"items": [], "color": None, "tip_color": None},
        "brows": {"items": [], "color": None, "tip_color": None},
        "facial_hair": {"items": [], "color": None, "tip_color": None},
        "colors": {"teeth": None, "gums": None, "nails": None, "lips": None},
        "clothing": [],
        "extras": [],
        "presets": [],
        "materials": [],
        "applied": {},
        "preset_file": None,
        "preset_of": None,
        "created": now(),
        "updated": now(),
    }


def traits_help() -> str:
    parts = []
    for category in ("body", "face"):
        names = ", ".join(t.name for t in TRAITS.values() if t.category == category)
        parts.append(f"{category.capitalize()}: {names}.")
    return " ".join(parts)


def worn_paths(sheet: dict) -> list[str]:
    out = list(sheet.get("clothing") or []) + list(sheet.get("extras") or [])
    for key in ("hair", "brows", "facial_hair"):
        out += list((sheet.get(key) or {}).get("items") or [])
    return out


def traits_of(sheet: dict) -> dict[str, float]:
    out: dict[str, float] = {}
    out.update(sheet.get("body") or {})
    out.update(sheet.get("face") or {})
    return {k: float(v) for k, v in out.items() if k in TRAITS}


def set_traits(sheet: dict, traits: dict[str, float | None]) -> None:
    for name, value in traits.items():
        trait = TRAITS[name]
        bucket = sheet.setdefault(trait.category, {})
        if value is None or abs(value) < 1e-9:
            bucket.pop(name, None)
        else:
            bucket[name] = round(float(value), 3)


def read_sheet(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("format") != SHEET_FORMAT:
        raise ValueError(f"{path} is not a Daz3D-MCP character sheet.")
    if int(data.get("version", 0)) > SHEET_VERSION:
        raise ValueError(f"{path} was written by a newer Daz3D-MCP (sheet version {data.get('version')}).")
    base = new_sheet(str(data.get("name") or path.stem))
    for key, value in data.items():
        if isinstance(base.get(key), dict) and isinstance(value, dict) and key not in ("body", "face", "dials",
                                                                                       "applied"):
            base[key] = {**base[key], **value}
        else:
            base[key] = value
    return base


def write_sheet(path: Path, sheet: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    sheet["updated"] = now()
    path.write_text(json.dumps(sheet, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def list_sheets(folder: Path) -> list[dict]:
    out = []
    if not folder.is_dir():
        return out
    for path in sorted(folder.glob("*.json")):
        try:
            sheet = read_sheet(path)
        except (OSError, ValueError):
            continue
        preset = folder / sheet["preset_file"] if sheet.get("preset_file") else None
        out.append({"name": sheet["name"], "sheet": path.as_posix(),
                    "generation": (sheet.get("figure") or {}).get("generation"),
                    "description": sheet.get("description"), "updated": sheet.get("updated"),
                    "preset": preset.as_posix() if preset and preset.is_file() else None})
    return out


DESCRIBING = ("figure", "body", "face", "height_cm", "dials", "skin", "eyes", "hair", "brows", "facial_hair",
              "colors", "clothing", "extras", "presets", "materials")


def content_hash(sheet: dict) -> str:
    data = {key: sheet.get(key) for key in DESCRIBING}
    return hashlib.sha1(json.dumps(data, sort_keys=True).encode("utf-8")).hexdigest()[:16]


def preset_current(sheet: dict) -> bool:
    return bool(sheet.get("preset_file")) and sheet.get("preset_of") == content_hash(sheet)


def unknown_in_sheet(sheet: dict) -> list[str]:
    return [k for k in list(sheet.get("body") or {}) + list(sheet.get("face") or {}) if k not in TRAITS]


def split_dial(key: str) -> tuple[Role, str]:
    head, sep, rest = key.partition(":")
    if sep and head.strip().lower() in ROLES and rest.strip():
        return head.strip().lower(), rest.strip()
    return "figure", key
