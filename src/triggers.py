"""
FiscAudit AI - Triggers voor een volledige fiscale toets

Bepaalt per dossier of een inhoudelijke analyse nodig is of niet. Dat is een
kostenafweging: een getal dat alleen juist overgenomen moet worden vraagt geen
modelaanroep, een bijzondere situatie wel.

De uitgangsregel: cijfermatig aansluiten gebeurt altijd en volledig in Python.
Een inhoudelijke toets komt er alleen bij wanneer een van de onderstaande
situaties wordt aangetroffen. Zo blijft een eenvoudig dossier goedkoop en
krijgt een dossier met een woningtransactie de aandacht die het nodig heeft.

De situaties komen uit de praktijk en zijn aangeleverd door de gebruiker. Ze
staan hier als tabel, zodat uitbreiden een regel toevoegen is.

WAT DEZE MODULE NIET DOET
Er staat geen fiscaal oordeel in. Een trigger zegt alleen: hier is meer aan de
hand dan een getal overtypen. Wat er fiscaal van geldt, komt uit de kennisbank
en de inhoudelijke weging.
"""

import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set

from .domain import RiskLevel


logger = logging.getLogger(__name__)


# ============================================================================
# SITUATIES
# ============================================================================

class TriggerKind(str, Enum):
    """Situatie die een volledige fiscale toets vraagt."""

    # eigen woning
    WONING_AANKOOP = "WONING_AANKOOP"
    WONING_VERKOOP = "WONING_VERKOOP"
    HYPOTHEEK_OVERGESLOTEN = "HYPOTHEEK_OVERGESLOTEN"
    ECHTSCHEIDING = "ECHTSCHEIDING"

    # onderneming
    ONDERNEMING_START = "ONDERNEMING_START"
    ONDERNEMING_STAKING = "ONDERNEMING_STAKING"
    OMZETTING = "OMZETTING"

    # verzekeringen en oudedag
    AOV_AFGESLOTEN = "AOV_AFGESLOTEN"
    AOV_UITKERING = "AOV_UITKERING"
    LIJFRENTE_AFGESLOTEN = "LIJFRENTE_AFGESLOTEN"
    LIJFRENTE_UITKERING = "LIJFRENTE_UITKERING"
    OUDEDAGSRESERVE = "OUDEDAGSRESERVE"

    @property
    def label(self) -> str:
        """Nederlandse omschrijving voor de interface."""
        return TRIGGER_DEFINITIES[self].label


@dataclass(frozen=True)
class TriggerDefinitie:
    """Beschrijving van een situatie en wat de toets moet omvatten.

    Attributes:
        label: Nederlandse omschrijving.
        rubriek: Groepering voor de reviewnote.
        basisrisico: Zwaarte zolang er geen bevinding is. Een woningverkoop
            is ook zonder aangetroffen fout een aandachtspunt, omdat de
            gevolgen doorwerken naar volgende jaren.
        toets_punten: Wat er inhoudelijk langs moet. Dit is de opdracht aan de
            weging, geen fiscaal oordeel. De onderwerpen zijn aangeleverd; wat
            er materieel van geldt komt uit de kennisbank.
        vereiste_stukken: Documenten die bij deze situatie in het dossier
            horen. Ontbreken die, dan is dat zelf een bevinding.
        raakt_volgend_jaar: True wanneer de situatie doorwerkt naar latere
            jaren en dus vastgelegd moet worden.
    """

    label: str
    rubriek: str
    basisrisico: RiskLevel
    toets_punten: List[str] = field(default_factory=list)
    vereiste_stukken: List[str] = field(default_factory=list)
    raakt_volgend_jaar: bool = False


TRIGGER_DEFINITIES: Dict[TriggerKind, TriggerDefinitie] = {

    # ---------------- eigen woning ----------------

    TriggerKind.WONING_AANKOOP: TriggerDefinitie(
        label="Aankoop eigen woning",
        rubriek="Eigen woning",
        basisrisico=RiskLevel.HIGH,
        toets_punten=[
            "splitsing van de kosten op de nota van afrekening tussen "
            "financieringskosten en aankoopkosten",
            "hoogte van de eigenwoningschuld en de onderbouwing daarvan",
            "toepassing van de bijleenregeling wanneer er een eerdere woning was",
            "eigenwoningforfait naar het aantal maanden eigendom",
        ],
        vereiste_stukken=[
            "nota van afrekening notaris",
            "hypotheekakte of hypotheekaanbod",
            "WOZ-beschikking van de nieuwe woning",
        ],
        raakt_volgend_jaar=True,
    ),

    TriggerKind.WONING_VERKOOP: TriggerDefinitie(
        label="Verkoop eigen woning",
        rubriek="Eigen woning",
        basisrisico=RiskLevel.HIGH,
        toets_punten=[
            "vaststelling van de overwaarde en de eigenwoningreserve",
            "gevolgen voor de renteaftrek bij een volgende woning",
            "eigenwoningforfait naar het aantal maanden eigendom",
            "afhandeling van de resterende schuld bij verkoop met onderwaarde",
        ],
        vereiste_stukken=[
            "nota van afrekening notaris",
            "aflossingsnota hypotheek",
        ],
        raakt_volgend_jaar=True,
    ),

    TriggerKind.HYPOTHEEK_OVERGESLOTEN: TriggerDefinitie(
        label="Hypotheek overgesloten",
        rubriek="Eigen woning",
        basisrisico=RiskLevel.MEDIUM,
        toets_punten=[
            "behandeling van de boeterente en de afsluitkosten",
            "of de schuld binnen de eigenwoningschuld blijft",
            "gevolgen voor een bestaand aflossingsschema",
        ],
        vereiste_stukken=[
            "afrekening oversluiting",
            "jaaropgave van de oude en de nieuwe geldverstrekker",
        ],
        raakt_volgend_jaar=True,
    ),

    TriggerKind.ECHTSCHEIDING: TriggerDefinitie(
        label="Echtscheiding of einde fiscaal partnerschap",
        rubriek="Eigen woning",
        basisrisico=RiskLevel.CRITICAL,
        toets_punten=[
            "keuze voor fiscaal partnerschap over het jaar en de gevolgen daarvan",
            "verdeling van de gezamenlijke posten in box 3",
            "verdeling van de eigenwoningschuld en de renteaftrek",
            "behandeling van partneralimentatie",
            "de woning als eigen woning bij de vertrekkende partner",
        ],
        vereiste_stukken=[
            "echtscheidingsbeschikking of vaststellingsovereenkomst",
            "afspraken over de woning",
        ],
        raakt_volgend_jaar=True,
    ),

    # ---------------- onderneming ----------------

    TriggerKind.ONDERNEMING_START: TriggerDefinitie(
        label="Start onderneming",
        rubriek="Onderneming",
        basisrisico=RiskLevel.HIGH,
        toets_punten=[
            "of aan het urencriterium wordt voldaan en of dat is onderbouwd",
            "toepassing van de startersfaciliteiten",
            "openingsbalans en de waardering van ingebrachte zaken",
            "investeringsaftrek over het eerste jaar",
        ],
        vereiste_stukken=[
            "inschrijving Kamer van Koophandel",
            "openingsbalans",
            "urenadministratie",
        ],
        raakt_volgend_jaar=True,
    ),

    TriggerKind.ONDERNEMING_STAKING: TriggerDefinitie(
        label="Staking onderneming",
        rubriek="Onderneming",
        basisrisico=RiskLevel.CRITICAL,
        toets_punten=[
            "vaststelling van de stakingswinst",
            "vrijval van reserves waaronder de oudedagsreserve en "
            "de herinvesteringsreserve",
            "afrekening over stille reserves en goodwill",
            "mogelijkheid tot omzetting van de stakingswinst in een lijfrente",
            "desinvesteringsbijtelling over eerdere investeringsaftrek",
        ],
        vereiste_stukken=[
            "eindbalans",
            "stakingsberekening",
        ],
        raakt_volgend_jaar=True,
    ),

    TriggerKind.OMZETTING: TriggerDefinitie(
        label="Omzetting onderneming, geruisloos of met afrekening",
        rubriek="Onderneming",
        basisrisico=RiskLevel.CRITICAL,
        toets_punten=[
            "of de gekozen route geruisloos of met afrekening is en of dat "
            "consequent is doorgevoerd",
            "of de voorwaarden voor de gekozen route zijn nageleefd",
            "behandeling van de reserves bij de overgang",
            "aansluiting tussen de eindbalans en de openingsbalans",
        ],
        vereiste_stukken=[
            "akte van oprichting",
            "inbrengbeschrijving",
            "verzoek of beschikking bij een geruisloze omzetting",
        ],
        raakt_volgend_jaar=True,
    ),

    # ---------------- verzekeringen en oudedag ----------------

    TriggerKind.AOV_AFGESLOTEN: TriggerDefinitie(
        label="Arbeidsongeschiktheidsverzekering afgesloten",
        rubriek="Verzekeringen en oudedag",
        basisrisico=RiskLevel.MEDIUM,
        toets_punten=[
            "of de premie in het juiste jaar in aftrek is gebracht",
            "of de polis aan de voorwaarden voor aftrek voldoet",
            "of alleen het aftrekbare deel van de premie is verwerkt",
        ],
        vereiste_stukken=["polisblad", "premieoverzicht of betaalbewijzen"],
    ),

    TriggerKind.AOV_UITKERING: TriggerDefinitie(
        label="Uitkering arbeidsongeschiktheidsverzekering",
        rubriek="Verzekeringen en oudedag",
        basisrisico=RiskLevel.HIGH,
        toets_punten=[
            "in welke rubriek de uitkering thuishoort",
            "of ingehouden loonheffing is verwerkt",
            "samenloop met andere inkomensbestanddelen",
        ],
        vereiste_stukken=["jaaropgave van de verzekeraar"],
    ),

    TriggerKind.LIJFRENTE_AFGESLOTEN: TriggerDefinitie(
        label="Lijfrente afgesloten of premie betaald",
        rubriek="Verzekeringen en oudedag",
        basisrisico=RiskLevel.HIGH,
        toets_punten=[
            "of er ruimte voor aftrek is en of die is onderbouwd",
            "of de aftrek in het juiste jaar valt",
            "of de betaling daadwerkelijk is verricht",
        ],
        vereiste_stukken=[
            "polis of overeenkomst",
            "berekening van de aftrekruimte",
            "betaalbewijs",
        ],
        raakt_volgend_jaar=True,
    ),

    TriggerKind.LIJFRENTE_UITKERING: TriggerDefinitie(
        label="Lijfrente-uitkering ontvangen",
        rubriek="Verzekeringen en oudedag",
        basisrisico=RiskLevel.MEDIUM,
        toets_punten=[
            "in welke rubriek de uitkering thuishoort",
            "of ingehouden loonheffing is verwerkt",
        ],
        vereiste_stukken=["jaaropgave van de uitkerende instelling"],
    ),

    TriggerKind.OUDEDAGSRESERVE: TriggerDefinitie(
        label="Oudedagsreserve toegevoegd of afgenomen",
        rubriek="Verzekeringen en oudedag",
        basisrisico=RiskLevel.HIGH,
        toets_punten=[
            "of aan de voorwaarden voor toevoeging is voldaan",
            "aansluiting van de stand met het voorgaande jaar",
            "of een afname op de juiste wijze is verwerkt",
        ],
        vereiste_stukken=["berekening van de stand", "aangifte voorgaand jaar"],
        raakt_volgend_jaar=True,
    ),
}


# ============================================================================
# UITKOMST
# ============================================================================

@dataclass
class Trigger:
    """Een aangetroffen situatie die een volledige fiscale toets vraagt."""

    kind: TriggerKind
    reden: str
    ontbrekende_stukken: List[str] = field(default_factory=list)

    @property
    def definitie(self) -> TriggerDefinitie:
        """De bijbehorende beschrijving."""
        return TRIGGER_DEFINITIES[self.kind]

    @property
    def risico(self) -> RiskLevel:
        """Zwaarte, verhoogd wanneer vereiste stukken ontbreken."""
        basis = self.definitie.basisrisico
        if not self.ontbrekende_stukken:
            return basis
        # Een bijzondere situatie zonder de bijbehorende stukken is niet te
        # beoordelen, en dat weegt zwaarder dan de situatie zelf.
        return RiskLevel.CRITICAL if basis == RiskLevel.HIGH else basis


@dataclass
class TriggerReport:
    """Alle aangetroffen situaties in een dossier."""

    triggers: List[Trigger] = field(default_factory=list)

    @property
    def needs_fiscal_analysis(self) -> bool:
        """Of er een inhoudelijke weging nodig is.

        Zonder trigger blijft het bij de cijfermatige aansluiting en wordt er
        geen modelaanroep gedaan.
        """
        return bool(self.triggers)

    @property
    def risico(self) -> RiskLevel:
        """Zwaarste risico onder de aangetroffen situaties."""
        return RiskLevel.highest(t.risico for t in self.triggers)

    @property
    def alle_toets_punten(self) -> List[str]:
        """Alles wat inhoudelijk langs moet, zonder dubbelingen."""
        gezien: Set[str] = set()
        punten: List[str] = []
        for trigger in self.triggers:
            for punt in trigger.definitie.toets_punten:
                if punt not in gezien:
                    gezien.add(punt)
                    punten.append(punt)
        return punten

    @property
    def alle_ontbrekende_stukken(self) -> List[str]:
        """Op te vragen stukken, zonder dubbelingen."""
        gezien: Set[str] = set()
        stukken: List[str] = []
        for trigger in self.triggers:
            for stuk in trigger.ontbrekende_stukken:
                if stuk not in gezien:
                    gezien.add(stuk)
                    stukken.append(stuk)
        return stukken

    @property
    def raakt_volgend_jaar(self) -> List[Trigger]:
        """Situaties die vastgelegd moeten worden voor latere jaren.

        De bijleenregeling en de oudedagsreserve zijn niet te controleren
        zonder de gegevens van eerdere jaren. Deze lijst is bedoeld om die
        gegevens nu vast te leggen, zodat de controle volgend jaar wel kan.
        """
        return [t for t in self.triggers if t.definitie.raakt_volgend_jaar]


# ============================================================================
# DETECTIE
# ============================================================================

def missing_documents(kind: TriggerKind, aanwezige_stukken: List[str]) -> List[str]:
    """Welke vereiste stukken ontbreken bij deze situatie.

    De vergelijking is op losse woorden en negeert hoofdletters, leestekens en
    scheidingstekens, omdat de bestandsnamen en documentaanduidingen in de
    praktijk niet exact overeenkomen met de omschrijvingen in de tabel.
    "WOZ-beschikking" moet ook aanslaan op "WOZ beschikking Kerkstraat.pdf" en
    op "woz_beschikking.pdf".

    Args:
        kind: De aangetroffen situatie.
        aanwezige_stukken: Aanduidingen of bestandsnamen van de aanwezige stukken.

    Returns:
        De omschrijvingen van de stukken die niet zijn aangetroffen.
    """
    aanwezig = _kernwoorden(" ".join(aanwezige_stukken))
    ontbreekt = []

    for vereist in TRIGGER_DEFINITIES[kind].vereiste_stukken:
        gevraagd = _kernwoorden(vereist)
        # Een stuk geldt als aanwezig zodra een van de kernwoorden voorkomt.
        # Een bestandsnaam bevat vrijwel nooit de volledige omschrijving.
        if gevraagd and not (gevraagd & aanwezig):
            ontbreekt.append(vereist)

    return ontbreekt


_VULWOORDEN = frozenset({
    "van", "over", "voor", "bij", "het", "de", "een", "en", "of",
    "nieuwe", "oude", "pdf", "docx",
})


def _kernwoorden(tekst: str) -> Set[str]:
    """Splits tekst in kernwoorden, los van leestekens en hoofdletters.

    Splitst op alles wat geen letter of cijfer is, zodat een streepje, een
    liggend streepje en een punt allemaal als scheiding gelden.
    """
    woorden = re.split(r"[^0-9a-z]+", tekst.lower())
    return {w for w in woorden if len(w) > 2 and w not in _VULWOORDEN}
