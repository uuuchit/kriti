import asyncio
from pipelines.narration2video_pipeline import Narration2VideoPipeline

NARRATION = """
जब पूरे ब्रह्मांड में देवता जन्म ले रहे थे, तभी एक वानर रूप में जन्मा शिव का अंश। एक वानर…लेकिन साधारण नहीं। वायु का पुत्र, शिव का अंश, और श्रीराम का सबसे प्रिय भक्त।
माता अंजनी ने वर्षों तक भगवान शिव की कठोर तपस्या की। उनकी एक ही प्रार्थना थी - "हे प्रभु, मुझे ऐसा पुत्र दीजिए जो आपकी भक्ति का प्रतीक बने।"
उधर अयोध्या में राजा दशरथ ने पुत्रेष्टि यज्ञ कराया। उस यज्ञ का दिव्य पायस जब वायु देव के माध्यम से अंजनी माता तक पहुँचा, तो उसी क्षण प्रकट हुए - एक तेजस्वी बालक, जिसका शरीर सोने सा दमकता था, और आँखों में अग्नि सी चमक थी। देवताओं ने घोषणा की - "यह वायु का पुत्र है, इसमें स्वयं महादेव का अंश है, और इसका नाम होगा - हनुमान।" भगवान शिव ने उसे अद्भुत शक्ति दी, वायु देव ने गति, सूर्य देव ने तेज, और ब्रह्मा ने वरदान - "जब तक श्रीराम का नाम रहेगा, तब तक तुम अमर रहोगे।"
हनुमान जी का जन्म केवल शक्ति का नहीं, भक्ति के जन्म का प्रतीक है। वो सिखाते हैं - सच्चा बल शरीर से नहीं, समर्पण और विनम्रता से आता है। अगली बार जानेंगे वो दिलचस्प कहानी, जब इस बाल हनुमान ने सूरज को ही निगल लिया था।
"""

USER_REQUIREMENT = """
Indian mythology style. Keep it to 4-6 shots max. Each shot should match one narration beat.
"""

STYLE = "Indian Mythology, Epic, Warm Golden Tones, Devotional, Cinematic"


async def main():
    pipeline = Narration2VideoPipeline.init_from_config(
        config_path="configs/narration2video.yaml"
    )
    await pipeline(
        narration=NARRATION,
        user_requirement=USER_REQUIREMENT,
        style=STYLE,
    )


if __name__ == "__main__":
    asyncio.run(main())
