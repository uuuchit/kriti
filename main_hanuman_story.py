import asyncio
from pipelines.script2video_pipeline import Script2VideoPipeline

# Story S1 from image-stories-str sample_stories_v3: हनुमान जी का जन्म और बचपन
script = \
"""
EXT. HEAVENLY REALM - DAWN
The cosmos is alive with divine energy. Gods are being born across the universe. Mata Anjani (ageless, divine, serene face, draped in white saree) is deep in meditation before a Shiva lingam on a mountain peak. Wind swirls around her.
NARRATOR: (V.O.) जब पूरे ब्रह्मांड में देवता जन्म ले रहे थे, तभी एक वानर रूप में जन्मा शिव का अंश।
A divine golden light descends from the sky. Vayu Dev (muscular, glowing, flowing robes) carries sacred payasam to Anjani. She receives it with folded hands. A brilliant golden baby appears - baby Hanuman (infant, golden-skinned, monkey features, radiant eyes).
NARRATOR: (V.O.) वायु का पुत्र, शिव का अंश, और श्रीराम का सबसे प्रिय भक्त।
The gods gather in the sky, showering blessings. Brahma, Surya Dev, and Shiva appear as celestial visions above.

EXT. ANJANI'S MOUNTAIN HOME - MORNING
Baby Hanuman (toddler, golden-skinned, playful, monkey tail) sits in Mata Anjani's lap. The red morning sun rises on the horizon. Baby Hanuman looks up at the sun with wide curious eyes.
BABY HANUMAN: (pointing at the sun, excited) क्या सुंदर लाल फल है! मैं इसे खा लूँ?
He leaps into the sky with incredible speed. Vayu Dev watches from below and supports his son with wind currents. Baby Hanuman flies higher and higher, reaching the sun. He opens his mouth wide and swallows the entire sun. Darkness engulfs the universe.

EXT. COSMIC VOID - CONTINUOUS
Complete darkness. The gods panic. Indra Dev (armored, crown, wielding vajra/thunderbolt) hurls his vajra at baby Hanuman. The thunderbolt strikes Hanuman's chin. Baby Hanuman falls unconscious.
Vayu Dev catches his son, enraged. He stops all wind in the universe. Everything begins to suffocate.
The gods rush to Vayu Dev, fold their hands in apology. One by one, each god grants Hanuman a boon.
BRAHMA: (with authority) जब तक श्रीराम का नाम रहेगा, तब तक तुम अमर रहोगे।

EXT. FOREST ASHRAM - DAY
Young Hanuman (child, 8 years old, mischievous, strong, monkey features) runs through a forest ashram causing chaos. He uproots small trees playfully, disrupts meditating rishis (elderly sages in saffron robes).
YOUNG HANUMAN: (laughing) मैं तो बस खेल रहा था!
The rishis gather, frustrated but compassionate.
HEAD RISHI: (raising hand solemnly) हे बालक, जब तक कोई तुझे तेरी शक्ति की याद न दिलाए, तू अपनी शक्ति को स्वयं नहीं पहचान पाएगा।
Young Hanuman suddenly becomes calm, humble. He sits quietly, the fire in his eyes dimming to gentle warmth.
NARRATOR: (V.O.) विनम्रता ही सच्ची शक्ति है।
"""

user_requirement = \
"""
Mythological Indian style. Keep it to 3-4 scenes max, 10-12 shots total. 
Warm golden color palette. Epic and devotional mood.
"""
style = "Indian Mythology, Epic, Warm Golden Tones, Devotional"


async def main():
    pipeline = Script2VideoPipeline.init_from_config(
        config_path="configs/script2video.yaml")
    await pipeline(script=script, user_requirement=user_requirement, style=style)

if __name__ == "__main__":
    asyncio.run(main())
