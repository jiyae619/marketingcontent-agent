import { PlatformPreview } from './PlatformPreview';

export default {
    title: 'Components/PlatformPreview',
    component: PlatformPreview,
    argTypes: {
        platform: {
            control: 'select',
            options: ['linkedin', 'instagram', 'circle', 'kakaotalk'],
        },
    },
};

const sampleContent = {
    linkedin: `Excited to announce our latest innovation! 🚀

We've been working hard to bring you something special. Check out our new features:

• Enhanced performance
• Better user experience
• Seamless integration

#Innovation #Technology #ProductLaunch`,

    instagram: `New launch alert! ✨ We're thrilled to share our latest creation with you. Swipe to see what's new! 

#NewProduct #Innovation #TechLife #Excited`,

    circle: `## Exciting News from Our Team! 🎉

We're thrilled to announce our latest product update. Here's what's new:

• Feature 1: Enhanced capabilities
• Feature 2: Improved performance
• Feature 3: Better integration

Join the conversation and let us know what you think!`,

    kakaotalk: `안녕하세요! 새로운 소식이 있어요 ✨ 
우리의 최신 업데이트를 확인해보세요!`,
};

export const LinkedIn = {
    args: {
        platform: 'linkedin',
        content: sampleContent.linkedin,
    },
};

export const Instagram = {
    args: {
        platform: 'instagram',
        content: sampleContent.instagram,
    },
};

export const Circle = {
    args: {
        platform: 'circle',
        content: sampleContent.circle,
    },
};

export const Kakaotalk = {
    args: {
        platform: 'kakaotalk',
        content: sampleContent.kakaotalk,
    },
};

export const Empty = {
    args: {
        platform: 'linkedin',
        content: '',
    },
};
