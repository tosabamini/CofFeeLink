# CofFeeLink

CofFeeLink is an experimental coffee extraction interface that turns hand-drip brewing into an embodied dialogue between you and the coffee. Instead of watching timers and scales, the brewer wears an eye mask and headphones to focus on aroma, sound and heat. Sensors record the brewer’s physiological responses (electrodermal activity and heart rate), and these signals modulate extraction parameters like stirring speed, pour duration and water volume in real time.

## Overview

CofFeeLink was developed to explore how internal sensory and emotional responses can shape the flavour of coffee. During brewing, the system monitors the user’s psychophysiological state via BITalino sensors and uses this to adjust how vigorously the coffee bed is agitated, how long water is poured, and how much water is used. The resulting cup reflects the brewer’s internal state, creating a personal, immersive brewing experience.

## Background and Motivation

Coffee engages multiple senses, especially aroma, which strongly influences mood. Although hand‑drip brewing is prized for its controllability, most devices depend on external metrics and visual feedback. Prior research shows that sensory stimuli such as smell and warmth affect autonomic responses, yet few systems allow these internal responses to influence the act of brewing. CofFeeLink reimagines coffee extraction as a dynamic, bidirectional interaction where your bodily reactions help shape the final brew.

## System Design

Participants are seated with the extraction apparatus, fitted with an eye mask and headphones to block visual distractions. A BITalino board captures electrodermal activity (EDA) and electrocardiogram (ECG) signals, which are streamed to a Raspberry Pi. Features such as skin conductance level, skin conductance responses and heartbeat variability are used to estimate the brewer’s relaxation–arousal state. These estimates drive three control variables:

- **Stirring speed:** a servo motor adjusts how vigorously the grounds are agitated.
- **Extraction time:** a solenoid valve sets the duration of each pour.
- **Water volume:** the valve also controls how much water flows through the coffee.

The feedback loop begins when the participant smells the coffee grounds, triggering physiological changes that determine the first pour conditions. As aromas, sounds and warmth from the brewing process provide new stimuli, the brewer’s responses continuously adjust subsequent pours.

## Experience Flow

The experience starts with a baseline measurement of the participant’s EDA and ECG. Brewing then proceeds through fragrance, first pour and second pour phases. Throughout the process, the participant’s physiological state influences the machine’s actions. After brewing, the sensors are removed and the participant receives a “coffee profile card” summarising the coffee origin, roast and extraction parameters alongside their physiological data. Real‑time visualisations on a nearby monitor show how internal responses influence the extraction.

## Significance and Future Work

By integrating biofeedback into the craft of coffee brewing, CofFeeLink encourages users to become aware of how sensory stimuli affect their bodies and, in turn, how their bodies can shape a drink. Future work will refine the mapping between physiological indicators and extraction parameters, explore additional sensors (e.g. respiration) and study how this embodied interaction influences perceptions of flavour, relaxation and engagement.
